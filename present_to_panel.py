"""Interactive local presentation guide; the submission package is unchanged."""
from pathlib import Path
import json
import os
import subprocess
import sys

PROJECT = Path(__file__).resolve().parent / 'support-ticket-assistant'
sys.path.insert(0, str(PROJECT))
from ticket_assistant.engine import SearchEngine, load_tickets
from ticket_assistant.__main__ import _show_result


def page(title):
    os.system('cls' if os.name == 'nt' else 'clear')
    print('SUPPORT TICKET SIMILARITY ASSISTANT')
    print(title)
    print('=' * 72)


def next_page(label='Press Enter to continue, or Ctrl+C to finish...'):
    input('\n' + label)


def load_demo():
    records = load_tickets(PROJECT / 'data' / 'tickets.json')
    engine = SearchEngine(records, 'solari-seed')
    examples = json.loads((PROJECT / 'data' / 'new_tickets_example.json').read_text(encoding='utf-8'))['new_tickets']
    return records, engine, {record['ticket_id']: record for record in examples}


def check():
    records, engine, examples = load_demo()
    assert len(records) == 40
    expected_first = {'NT-1': None, 'NT-2': 'T-1201', 'NT-3': 'T-1303', 'NT-4': None}
    for identifier, expected in expected_first.items():
        source = examples[identifier]
        result = engine.search(source['subject'], source['description'], exclude_ticket_id=identifier)
        first = result['results'][0]['ticket']['id'] if result['results'] else None
        assert first == expected, (identifier, first, expected)
        print(f'{identifier}: {first or "No suggestion"}')
    assert (PROJECT / 'verification' / 'evaluation.json').is_file()
    assert (PROJECT / 'verification' / 'benchmark.json').is_file()
    print('Presentation launcher check passed. All four inputs use the supplied files.')


def main():
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11 or newer is required.')
    if '--check' in sys.argv:
        check()
        return
    records, engine, examples = load_demo()
    page('1 of 7  |  Customer problem and scope')
    print('Goal: help support agents find useful prior fixes and answer consistently.')
    print(f'Data: {len(records)} supplied historical tickets and four incoming examples.')
    print('Approach: explainable BM25 retrieval using titles and descriptions.')
    print('Output: original source cases and resolutions; the agent verifies the fix.')
    print('\nThis is a working local prototype with a CLI, batch flow, and local API.')
    print('The next four screens run live retrieval against the unchanged seed data.')
    next_page('Share this terminal window, then press Enter for the first live case...')

    notes = {
        'NT-3': 'Explain: the source is useful evidence; inspect actual payment events before applying its fix.',
        'NT-2': 'Explain: T-1201 is useful. T-1501 is a weaker permission-related match, a known precision limit.',
        'NT-4': 'Explain: there is no strong Snowflake history. The general evidence gate returns no suggestion.',
        'NT-1': 'Explain: a missing reset email differs from a rejected password after receiving the email.',
    }
    for screen, identifier in enumerate(('NT-3', 'NT-2', 'NT-4', 'NT-1'), start=2):
        source = examples[identifier]
        page(f'{screen} of 7  |  Live incoming ticket {identifier}')
        print(source['subject'])
        print(source['description'])
        result = engine.search(source['subject'], source['description'], exclude_ticket_id=identifier)
        _show_result(result)
        print('\n' + notes[identifier])
        next_page()

    page('6 of 7  |  Verification and limits')
    print('Run the existing functional tests live:')
    print('python -m unittest discover -s tests -q')
    answer = input('\nPress Enter to run them, or type skip: ').strip().lower()
    if answer != 'skip':
        outcome = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'], cwd=PROJECT, check=False)
        print(f'\nActual test process exit code: {outcome.returncode}')
    report = json.loads((PROJECT / 'verification' / 'evaluation.json').read_text(encoding='utf-8'))
    metrics = report['provided_examples']['metrics']
    print('\nRecorded evaluation, not a new run:')
    print(f"  Supplied known-source examples: {metrics['known_source_hits_at_3']}/{metrics['known_source_examples']} retrieved a labeled source.")
    print(f"  Labeled suggestions across those examples: {metrics['labeled_known_source_suggestions']}/{metrics['total_known_source_suggestions']}.")
    print('  One authored hard negative returns an incorrect chart fix.')
    print('  These local relevance judgments are not a customer accuracy benchmark.')
    print('  evaluate.py exits 1 to expose the retained relevance failure.')
    next_page()

    page('7 of 7  |  Design choices and next steps')
    benchmark = json.loads((PROJECT / 'verification' / 'benchmark.json').read_text(encoding='utf-8'))
    print('Why this design: local, explainable, no external model dependency.')
    print('Known gaps: negation, paraphrases, noisy candidates, snapshot-only updates.')
    print('The seed has no customer identities or resolution dates; none are invented.')
    print(f"\nRecorded artificial 55,000-record warm-search p95: {benchmark['timing']['p95_ms']:.0f} ms.")
    print('This exceeds the proposed 500 ms target before HTTP overhead.')
    print('It is repeated seed text, not a production capacity test.')
    print('\nNext: independent relevance labels, agent pilot, authenticated helpdesk')
    print('integration, permission checks, and profiling against realistic traffic.')
    print('\nFor code questions: ticket_assistant/engine.py')
    print('For architecture: SOLUTION_DESIGN.md')
    print('For measured results: VALIDATION.md')
    print('\nDemo complete. Invite questions and explain each tradeoff in your own words.')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nPresentation stopped.')
