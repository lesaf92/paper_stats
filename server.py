from flask import Flask, render_template, request, flash, jsonify, redirect, url_for, Response, abort
from datetime import datetime
import csv
import io
import json
import os
import threading

import collector

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(16)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
JOURNALS_FILE = os.path.join(BASE_DIR, 'list_of_journals.txt')
RESULTS_FILE = os.path.join(BASE_DIR, 'results.json')
DEFAULT_CONFIG = {"num_samples": 10, "year_start": 2020, "year_end": 2025, "mine_pdfs": True}
MAX_SAMPLES_PER_JOURNAL = 100
MIN_PUBLICATION_YEAR = 1900
MAX_PUBLICATION_YEAR = datetime.now().year + 1
CSV_FIELDS = ['journal', 'title', 'doi', 'link', 'source', 'received', 'accepted', 'review_days',
              'submitted', 'published', 'proxy_days']
# Public deployments only serve the committed results.json. On Vercel (which sets VERCEL=1) a run
# would outlive the function and couldn't save anything, and strangers shouldn't start 30-minute jobs.
READ_ONLY = os.environ.get('READ_ONLY') == '1' or os.environ.get('VERCEL') == '1'

job = {'running': False, 'progress': 0.0, 'message': ''}
job_lock = threading.Lock()


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                return {**DEFAULT_CONFIG, **json.load(f)}
            except json.JSONDecodeError:
                pass
    return dict(DEFAULT_CONFIG)


def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


def load_journals():
    if os.path.exists(JOURNALS_FILE):
        with open(JOURNALS_FILE, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    return []


def load_results():
    try:
        with open(RESULTS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def run_job(config, journals):
    try:
        papers = collector.collect(journals, config,
                                   lambda fraction, message: job.update(progress=fraction, message=message))
        tmp = RESULTS_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump({'finished': datetime.now().isoformat(timespec='seconds'), 'config': config,
                       'papers': papers}, f, indent=1)
        os.replace(tmp, RESULTS_FILE)
    except Exception as e:
        job['message'] = f'Analysis failed: {e}'
        raise
    finally:
        job['running'] = False


@app.before_request
def block_writes_when_read_only():
    if READ_ONLY and request.method == 'POST':
        abort(403)


@app.route('/')
def index():
    results = load_results()
    papers = results['papers'] if results else None
    return render_template('index.html', papers=papers, results=results, job=job, journals=load_journals(),
                           config=load_config(), summary=collector.summarize(papers) if papers else None,
                           read_only=READ_ONLY, max_samples=MAX_SAMPLES_PER_JOURNAL,
                           min_year=MIN_PUBLICATION_YEAR, max_year=MAX_PUBLICATION_YEAR)


@app.route('/run', methods=['POST'])
def run():
    journals = load_journals()
    if not journals:
        flash('No journals found in list_of_journals.txt.')
        return redirect(url_for('index'))
    with job_lock:
        if not job['running']:
            job.update(running=True, progress=0.0, message='Starting...')
            threading.Thread(target=run_job, args=(load_config(), journals), daemon=True).start()
    return redirect(url_for('index'))


@app.route('/status')
def status():
    return jsonify(job)


@app.route('/results.csv')
def results_csv():
    results = load_results()
    if not results:
        flash('No results yet. Run the analysis first.')
        return redirect(url_for('index'))
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_FIELDS, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(results['papers'])
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=paper_stats.csv'})


@app.route('/save_config', methods=['POST'])
def save_config_route():
    try:
        config = {
            "num_samples": int(request.form.get('num_samples', DEFAULT_CONFIG['num_samples'])),
            "year_start": int(request.form.get('year_start', DEFAULT_CONFIG['year_start'])),
            "year_end": int(request.form.get('year_end', DEFAULT_CONFIG['year_end'])),
            "mine_pdfs": 'mine_pdfs' in request.form,
        }
    except (TypeError, ValueError):
        flash('Sample count and publication years must be whole numbers.')
        return redirect(url_for('index'))

    valid_samples = 1 <= config['num_samples'] <= MAX_SAMPLES_PER_JOURNAL
    valid_years = (MIN_PUBLICATION_YEAR <= config['year_start'] <= config['year_end']
                   <= MAX_PUBLICATION_YEAR)
    if not valid_samples or not valid_years:
        flash(f'Use 1–{MAX_SAMPLES_PER_JOURNAL} papers per journal and years from '
              f'{MIN_PUBLICATION_YEAR} to {MAX_PUBLICATION_YEAR}, with the start year no later than the end year.')
        return redirect(url_for('index'))
    save_config(config)
    flash('Configuration saved successfully!')
    return redirect(url_for('index'))


if __name__ == '__main__':
    # The Werkzeug debugger runs arbitrary code, so keep it local unless asked: FLASK_DEBUG=1, HOST=0.0.0.0
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1', host=os.environ.get('HOST', '127.0.0.1'), port=5000)
