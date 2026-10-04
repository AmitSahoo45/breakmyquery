"""BreakMyQuery: SQLite-verified evidence, with local or hosted model proposals."""

from collections import Counter
from dataclasses import replace
import json
import sqlite3

import pandas as pd
import streamlit as st

from bmq import hunter, journal, llm, tutor
from bmq.config import ROOT, get_settings
from bmq.db import table_columns


st.set_page_config(page_title='BreakMyQuery', page_icon='↯', layout='wide')
st.html('''<style>
    .block-container { max-width: 1120px; padding-top: 2rem; }
    [data-testid="stTextArea"] textarea { font-family: ui-monospace, Consolas, monospace; }
    [data-testid="stMetricValue"] { font-size: 1.6rem; }
</style>''')


def show_dataset(dataset):
    """Render only table rows and schema-derived column names."""
    populated = False
    for table, columns in table_columns().items():
        rows = dataset.get(table, [])
        if rows:
            populated = True
            st.caption(table)
            st.dataframe(pd.DataFrame(rows, columns=columns), hide_index=True, width='stretch')
    if not populated:
        st.caption('All tables are empty. Empty data can also expose a bug.')


def result_frame(result, marked_rows, label):
    # SQLite permits duplicate/blank aliases; Arrow requires unique labels.
    names, used = [], {'Difference'}
    for index, name in enumerate(result.columns, 1):
        candidate = name or f'Column {index}'
        while candidate in used:
            candidate += f' ({index})'
        used.add(candidate)
        names.append(candidate)
    counts = Counter(tuple(row) for row in marked_rows)
    marks = []
    for row in result.rows:
        normalized = tuple(round(value, 6) if isinstance(value, float) else value for value in row)
        marks.append(label if counts[normalized] else '')
        if counts[normalized]:
            counts[normalized] -= 1
    frame = pd.DataFrame(result.rows, columns=names)
    frame.insert(0, 'Difference', marks)
    return frame


def show_result(result, marked, label):
    frame = result_frame(result, marked, label)
    # A text marker supplements the color so the distinction is accessible.
    styled = frame.style.apply(
        lambda row: ['background-color: #493522' if row.iloc[0] else '' for _ in row], axis=1,
    )
    st.dataframe(styled, hide_index=True, width='stretch')
    st.caption(f'{len(result.rows)} row(s)')


def switch_exercise():
    state = st.session_state
    save_draft()
    state.active_exercise = state.exercise_id
    state.sql_editor = state.drafts.get(state.exercise_id, '')
    state.attempt = None


def save_draft():
    state = st.session_state
    if 'sql_editor' in state:
        state.drafts[state.active_exercise] = state.sql_editor


def retry(exercise_id, sql):
    state = st.session_state
    save_draft()
    state.page = 'Practice'
    state.exercise_id = state.active_exercise = exercise_id
    state.drafts[exercise_id] = state.sql_editor = sql
    state.attempt = None


def show_hints(attempt, settings):
    if not settings.model_hints:
        st.caption('Model hints are off. Compare the highlighted rows to investigate this case.')
        return
    future = attempt['future']
    pending = future is not None and not future.done()

    @st.fragment(run_every=0.5 if pending else None)
    def hint_panel():
        if future is not None and not future.done():
            st.caption('Preparing optional hints locally… Your counterexample is ready above.')
            return
        if future is not None and attempt['explanation_result'] is None:
            try:
                attempt['explanation_result'] = future.result()
            except Exception:
                # Model failures must not erase verified SQLite evidence.
                attempt['explanation_result'] = tutor.ExplanationResult(None)
            # Stop periodic polling and refresh journal/sidebar state.
            st.rerun()
        result = attempt['explanation_result']
        explanation = result.explanation if result else None
        if result and not result.journal_saved:
            st.warning('The explanation could not be saved to your local journal.')
        if explanation is None:
            st.caption('Hints unavailable. Compare the highlighted rows to investigate this case.')
            return
        if st.button('Nudge me', key=f'nudge_{attempt["token"]}'):
            attempt['hint_level'] = max(1, attempt['hint_level'])
        if attempt['hint_level'] >= 1:
            st.text(llm.safe_text(explanation.what_happened))
            st.text(llm.safe_text(explanation.nudge))
            if attempt['verdict'].gemma_idea:
                st.text('Model’s idea: ' + llm.safe_text(attempt['verdict'].gemma_idea))
            if explanation.hint and st.button('Bigger hint', key=f'hint_{attempt["token"]}'):
                attempt['hint_level'] = 2
            if attempt['hint_level'] == 2 and explanation.hint:
                st.text(llm.safe_text(explanation.hint))

    hint_panel()


def show_verdict(attempt, schema, settings):
    verdict = attempt['verdict']
    st.divider()
    st.subheader('Your last run')
    with st.expander('Query used for this result'):
        st.code(attempt['sql'], language='sql')
    if verdict.stats.get('model_note'):
        # The hunter supplies fixed status text, never a provider error body.
        st.info(verdict.stats['model_note'])
    if verdict.status == 'ERROR':
        st.error('Your query could not run.')
        st.text(verdict.error)
        if settings.model_hints and st.button('Explain this error', disabled=not st.session_state.model_online):
            if not attempt['error_requested']:
                with st.spinner('The local model is explaining the error…'):
                    attempt['error_explanation'] = llm.explain_error(
                        schema, attempt['sql'], verdict.error, settings=settings,
                    )
                attempt['error_requested'] = True
        if settings.model_hints and attempt['error_requested']:
            explanation = attempt['error_explanation']
            if explanation:
                st.text(llm.safe_text(explanation.meaning))
                st.text(llm.safe_text(explanation.where_to_look))
            else:
                st.caption('Explanation unavailable. Check the SQLite message above.')
    elif verdict.status == 'PASSED':
        count = verdict.stats.get('gemma_candidates', 0) + verdict.stats.get('fuzz_tries', 0)
        st.success(f'Passed sample + {count} stress tests. No breaking case found.')
        if not count:
            st.warning('No stress datasets were verified. This run only checked the sample.')
    else:
        st.error('Wrong on the sample data.' if verdict.status == 'WRONG_ON_SAMPLE'
                 else 'Your query passes the sample data — but it breaks here.')
        st.subheader('The breaking case')
        show_dataset(verdict.dataset)
        st.caption('Shrunk by removing rows while the mismatch remains. '
                   'This search does not guarantee the smallest possible dataset.')
        if verdict.found_by == 'gemma':
            source = f'Found by {settings.model}.'
            if settings.model_hints:
                source += ' Reveal a nudge to see its idea.'
            st.caption(source)
        elif verdict.found_by == 'fuzz':
            st.caption('Found by random stress test')
        else:
            st.caption('A failing slice of the sample data')
        yours, expected = st.columns(2)
        with yours:
            st.markdown('**Your result**')
            show_result(verdict.learner_result, verdict.diff.extra, 'Extra')
        with expected:
            st.markdown('**Expected result**')
            show_result(verdict.expected_result, verdict.diff.missing, 'Missing')
        if verdict.diff.column_count_mismatch:
            st.warning('The number of result columns differs.')
        elif not verdict.diff.missing and not verdict.diff.extra:
            st.warning('The rows match as a collection, but their order differs.')
        show_hints(attempt, settings)


def practice(exercise, schema, settings, history):
    st.title(exercise['title'])
    st.write(exercise['question'])
    with st.expander('Database schema'):
        st.code(schema, language='sql')
    with st.expander('Sample data', expanded=True):
        show_dataset(exercise['sample_data'])
    if 'sql_editor' not in st.session_state:
        st.session_state.sql_editor = st.session_state.drafts.get(exercise['id'], '')
    st.text_area('Your SQL', key='sql_editor', height=210,
                 placeholder='Write a SQLite SELECT query…', max_chars=4_000 if settings.public_demo else 100_000)
    if settings.model_provider == 'gemini':
        st.caption('SQLite verifies results on this server. Your SQL is sent to Google for test-data proposals. '
                   'Google may use free-tier inputs and outputs to improve its products. '
                   'Use practice queries without private information.')
    elif settings.public_demo:
        st.caption('Read-only SQLite · duplicate rows matter · processing runs on this server')
    else:
        st.caption('Read-only SQLite · duplicate rows matter · everything runs locally')
    if st.button('Run', type='primary', width='content'):
        sql = st.session_state.sql_editor
        if settings.public_demo and len(sql) > 4_000:
            st.warning('Keep your query within 4,000 characters for this public demo.')
            return
        st.session_state.drafts[exercise['id']] = sql
        st.session_state.journal_warning = None
        st.session_state.model_online = llm.model_available(settings)
        hunt_settings = settings if st.session_state.model_online else replace(settings, hunt_order=('fuzz',))
        with st.status('Running on sample…', expanded=True) as progress:
            verdict = hunter.check(exercise, sql, lambda stage, detail: progress.update(label=detail), settings=hunt_settings)
            progress.update(label='Run finished', state='complete', expanded=False)
        attempt_id = None
        try:
            attempt_id = history.log_attempt(exercise['id'], sql, verdict, settings=settings)
        except (OSError, sqlite3.Error, ValueError):
            st.session_state.journal_warning = ('This run could not be saved to your session history.'
                                                if settings.public_demo else
                                                'This run could not be saved to your local journal.')
        st.session_state.run_number += 1
        future = None
        if (not settings.public_demo and settings.model_hints and st.session_state.model_online
                and verdict.status in ('WRONG_ON_SAMPLE', 'HIDDEN_BUG')):
            future = tutor.submit_explanation(exercise['question'], schema, sql, verdict, attempt_id, settings=settings)
        st.session_state.attempt = {
            'verdict': verdict, 'sql': sql, 'future': future, 'explanation_result': None,
            'hint_level': 0, 'token': st.session_state.run_number,
            'error_requested': False, 'error_explanation': None,
        }
        st.rerun()
    if st.session_state.get('journal_warning'):
        st.warning(st.session_state.journal_warning)
    if st.session_state.attempt:
        show_verdict(st.session_state.attempt, schema, settings)


def traps(attempts, exercises, settings):
    st.title('My traps')
    st.write('Small counterexamples, remembered. Retry a query and test your next idea.')
    failures = [a for a in attempts if a['verdict'] in ('WRONG_ON_SAMPLE', 'HIDDEN_BUG')]
    if not failures:
        st.info('No traps yet. Run an exercise to start your session history.' if settings.public_demo
                else 'No traps yet. Run an exercise to start your local journal.')
        return
    titles = {e['id']: e['title'] for e in exercises}

    def group_key(attempt):
        return (attempt['mistake_type'] or 'Unclassified') if settings.model_hints else attempt['exercise_id']

    counts = Counter(group_key(a) for a in failures)
    axis = 'Mistake' if settings.model_hints else 'Exercise'
    labels = list(counts) if settings.model_hints else [titles.get(key, 'Unavailable exercise') for key in counts]
    st.bar_chart(pd.DataFrame({axis: labels, 'Attempts': list(counts.values())}),
                 x=axis, y='Attempts', horizontal=True, color='#b4f272')
    if settings.model_hints and counts['Unclassified']:
        st.caption('Unclassified attempts keep their evidence even when the model is unavailable.')
    if not settings.model_hints:
        st.caption('Model hints and mistake labels are hidden. Saved queries and evidence remain available.')
    seen = set()
    for attempt in failures:
        kind = group_key(attempt)
        if kind in seen:
            continue
        seen.add(kind)
        with st.container(border=True):
            label = kind if settings.model_hints else 'Evidence only'
            st.subheader(f'{label} · {counts[kind]}')
            st.write(titles.get(attempt['exercise_id'], 'Unavailable exercise'))
            st.caption(attempt['ts'])
            st.code(attempt['learner_sql'], language='sql')
            if attempt['counterexample'] is not None:
                show_dataset(attempt['counterexample'])
            if settings.model_hints and attempt['what_happened']:
                st.text(llm.safe_text(attempt['what_happened']))
            st.button('Retry', key=f'retry_{attempt["id"]}',
                      disabled=attempt['exercise_id'] not in titles,
                      on_click=retry, args=(attempt['exercise_id'], attempt['learner_sql']))


def main():
    try:
        settings = get_settings()
    except ValueError as error:
        st.error('Check the app configuration.')
        st.text(str(error))
        return
    exercises = json.loads((ROOT / 'data/exercises.json').read_text(encoding='utf-8'))
    schema = (ROOT / 'data/schema.sql').read_text(encoding='utf-8')
    state = st.session_state
    if 'drafts' not in state:
        state.drafts = {}
        state.page = 'Practice'
        state.exercise_id = state.active_exercise = exercises[0]['id']
        state.sql_editor = ''
        state.attempt = None
        state.run_number = 0
    if 'model_online' not in state:
        state.model_online = llm.model_available(settings)
    if settings.public_demo:
        if 'session_journal' not in state:
            state.session_journal = journal.SessionJournal()
        history = state.session_journal
    else:
        history = journal
    try:
        attempts = history.list_attempts(settings=settings)
    except (OSError, sqlite3.Error, ValueError):
        attempts = []
        st.warning('Session history could not be opened. Practice is still available.' if settings.public_demo
                   else 'The local journal could not be opened. Practice is still available.')
    latest = {}
    for attempt in attempts:
        latest.setdefault(attempt['exercise_id'], attempt['verdict'])
    statuses = {'PASSED': '✓ Passed checks', 'HIDDEN_BUG': '! Counterexample',
                'WRONG_ON_SAMPLE': '! Sample mismatch', 'ERROR': '× Query error'}
    titles = {e['id']: e['title'] for e in exercises}
    with st.sidebar:
        st.title('↯ BreakMyQuery')
        st.caption('Find the row that breaks your SQL.')
        st.radio('Page', ['Practice', 'My traps'], key='page', on_change=save_draft, label_visibility='collapsed')
        st.radio('Exercises', list(titles), key='exercise_id', on_change=switch_exercise,
                 format_func=lambda eid: titles[eid],
                 captions=[statuses.get(latest.get(eid), '○ Not run') for eid in titles])
        st.divider()
        if settings.model_provider == 'gemini':
            st.text(f'Model configured ({settings.model})' if state.model_online
                    else f'Model not configured: fuzz only ({settings.model})')
            st.caption('Requests depend on API access and available quota.')
        else:
            st.text(f'Model online ({settings.model})' if state.model_online
                    else f'Model offline: fuzz only ({settings.model})')
        if not settings.model_hints:
            st.caption('Evidence-only mode · model hints off')
        if st.button('Refresh model configuration' if settings.model_provider == 'gemini' else 'Refresh model status'):
            state.model_online = llm.model_available(settings)
            st.rerun()
        if settings.public_demo:
            st.caption('No account. Your last 50 attempts stay in this session only. '
                       'Refreshing, reconnecting or restarting the app can clear them. No solution reveals.')
        else:
            st.caption('No account. No solution reveals.' if settings.model_provider == 'gemini'
                       else 'Local practice. No account. No solution reveals.')
    if state.page == 'Practice':
        practice(next(e for e in exercises if e['id'] == state.exercise_id), schema, settings, history)
    else:
        traps(attempts, exercises, settings)


main()
