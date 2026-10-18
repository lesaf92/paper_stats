from flask import Flask, render_template, request, flash, jsonify, redirect, url_for, Response
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
CSV_FIELDS = ['journal', 'title', 'doi', 'link', 'source', 'received', 'accepted', 'review_days',
              'submitted', 'published', 'proxy_days']

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
        with open(RESULTS_FILE, 'w') as f:
            json.dump({'finished': datetime.now().isoformat(timespec='seconds'), 'config': config,
                       'papers': papers}, f, indent=1)
    except Exception as e:
        job['message'] = f'Analysis failed: {e}'
        raise
    finally:
        job['running'] = False


@app.route('/')
def index():
    results = load_results()
    papers = results['papers'] if results else None
    return render_template('index.html', papers=papers, results=results, job=job, journals=load_journals(),
                           config=load_config(), summary=collector.summarize(papers) if papers else None)


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
    config = {
        "num_samples": request.form.get('num_samples', 10, type=int),
        "year_start": request.form.get('year_start', 2020, type=int),
        "year_end": request.form.get('year_end', 2025, type=int),
        "mine_pdfs": 'mine_pdfs' in request.form,
    }
    if config['num_samples'] < 1 or config['year_start'] > config['year_end']:
        flash('Need at least 1 paper per journal and a start year no later than the end year.')
        return redirect(url_for('index'))
    save_config(config)
    flash('Configuration saved successfully!')
    return redirect(url_for('index'))


if __name__ == '__main__':
    # The Werkzeug debugger runs arbitrary code, so keep it local unless asked: FLASK_DEBUG=1, HOST=0.0.0.0
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1', host=os.environ.get('HOST', '127.0.0.1'), port=5000)
