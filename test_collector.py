"""Offline checks for the parsing and filtering in collector.py. Run: python test_collector.py"""
from collector import build_row, crossref_dates, dates_from_text, in_scope, normalize, parse_date, summarize


def test_parse_date():
    assert parse_date('24 February 2025') == '2025-02-24'
    assert parse_date('February 24, 2025') == '2025-02-24'
    assert parse_date('Feb. 24 2025') == '2025-02-24'
    assert parse_date('Sept. 3, 2021') == '2021-09-03'
    assert parse_date('2025-02-24') == '2025-02-24'
    assert parse_date('JULY , 2026') is None


def test_footnotes():
    # Real first-page text from arXiv PDFs: T-RO, RA-L, IEEE Access, Elsevier
    tro = 'Manuscript received February 24, 2025; revised August 19, 2025 and November 26, 2025; accepted February 7, 2026.'
    ral = ('VERSION. ACCEPTED JULY , 2026 1 Extending ... Manuscript received: April 14, 2026; '
           'Revised: June 17, 2026; Accepted: July 27, 2026. This paper was recommended')
    access = 'Received 6 June 2026, accepted 22 July 2026, date of publication 12 August 2026'
    elsevier = 'Article history: Received 12 March 2021 Received in revised form 2 June 2021 Accepted 9 July 2021'
    assert dates_from_text(tro) == ('2025-02-24', '2026-02-07')
    assert dates_from_text(ral) == ('2026-04-14', '2026-07-27')
    assert dates_from_text(access) == ('2026-06-06', '2026-07-22')
    assert dates_from_text(elsevier) == ('2021-03-12', '2021-07-09')
    assert dates_from_text('This article has been accepted for publication in IEEE Transactions on Robotics. 2026') == (None, None)


def test_crossref_dates():
    springer = {'assertion': [{'name': 'received', 'value': '16 May 2025'}, {'name': 'accepted', 'value': '31 December 2025'}],
                'published-online': {'date-parts': [[2026, 3, 31]]}}
    wiley = {'assertion': [{'name': 'received', 'value': '2023-12-07'}, {'name': 'accepted', 'value': '2025-02-16'}],
             'published-online': {'date-parts': [[2025, 3, 7]]}}
    ieee = {'created': {'date-parts': [[2026, 2, 17]]},
            'published-print': {'date-parts': [[2025, 12, 4]]}}
    created_only = {'created': {'date-parts': [[2026, 2, 17]]}}
    issued = {'created': {'date-parts': [[2026, 2, 17]]}, 'issued': {'date-parts': [[2024, 6, 2]]}}
    assert crossref_dates(springer) == ('2025-05-16', '2025-12-31', '2026-03-31')
    assert crossref_dates(wiley) == ('2023-12-07', '2025-02-16', '2025-03-07')
    assert crossref_dates(ieee) == (None, None, '2025-12-04')
    assert crossref_dates(created_only) == (None, None, None)
    assert crossref_dates(issued) == (None, None, '2024-06-02')


def test_venue_and_rows():
    assert normalize('The International Journal of Robotics Research') == normalize('International Journal of Robotics Research')
    assert normalize('Journal of Intelligent & Robotic Systems') == normalize('journal of intelligent and robotic systems')
    assert normalize('IEEE Robotics &amp; Automation Magazine') == normalize('IEEE Robotics and Automation Magazine')
    rec = {'venue': 'Annual Review of Control, Robotics, and Autonomous Systems', 'published': '2026-05-05',
           'received': None, 'accepted': None, 'source': None}
    assert not in_scope(rec, 'robotics and autonomous systems', 2022, 2026)
    rec['venue'] = 'Robotics and Autonomous Systems'
    assert in_scope(rec, 'robotics and autonomous systems', 2022, 2026)
    assert not in_scope(rec, 'robotics and autonomous systems', 2022, 2025)

    paper = {'title': 'T', 'link': 'L', 'doi': 'D', 'submitted': '2026-01-01'}
    row = build_row(paper, rec, 'j')
    assert (row['source'], row['review_days'], row['proxy_days']) == ('proxy', None, 124)
    rec.update(received='2025-01-01', accepted='2025-03-02', source='pdf')
    row = build_row(paper, rec, 'j')
    assert (row['source'], row['review_days']) == ('pdf', 60)
    rec.update(published='2025-12-01', accepted='2024-01-01')  # accepted before received, published before arXiv
    assert build_row(paper, rec, 'j') is None


def test_summarize():
    rows = [{'journal': 'slow', 'review_days': d, 'proxy_days': None} for d in (100, 200, 300)]
    rows += [{'journal': 'fast', 'review_days': 50, 'proxy_days': 80}, {'journal': 'none', 'review_days': None, 'proxy_days': 9}]
    s = summarize(rows)
    assert [x['journal'] for x in s] == ['fast', 'slow', 'none']
    assert s[1]['review'] == (150, 200, 250) and s[1]['measured'] == 3
    assert s[0]['review'] == (50, 50, 50) and s[2]['review'] == (None, None, None)


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
    print('All checks passed.')
