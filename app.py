"""Gewichtheben Tracker – lokale Streamlit-Anwendung für Sportvereine."""
from __future__ import annotations

from datetime import date, datetime
from io import StringIO
import csv
import hmac
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title='Gewichtheben | Vereinstracker', page_icon='🏋️', layout='wide',
                   initial_sidebar_state='expanded')

# Cloud credentials are configured only in Streamlit Secrets, never in GitHub.
def _secret(key):
    try:
        return st.secrets.get(key, os.getenv(key, ''))
    except FileNotFoundError:
        return os.getenv(key, '')


# A cloud deployment requires *both* distinct role passwords. APP_PASSWORD
# from previous releases is intentionally not accepted: sharing that old
# password must never silently confer administrator privileges.
from access_control import authenticate, can_edit, config_error, session_proof, session_valid

cloud_url = _secret('DATABASE_URL')
if cloud_url:
    os.environ['DATABASE_URL'] = cloud_url
    admin_password = str(_secret('ADMIN_PASSWORD'))
    viewer_password = str(_secret('VIEWER_PASSWORD'))
    problem = config_error(admin_password, viewer_password)
    if problem:
        st.error('Die Rollenanmeldung ist noch nicht eingerichtet: ' + problem)
        st.info('Bitte zuerst unter Streamlit Community Cloud → App → Settings → Secrets '
                'ADMIN_PASSWORD und VIEWER_PASSWORD ergänzen. DATABASE_URL unverändert lassen.')
        st.stop()

    role = st.session_state.get('auth_role')
    proof = st.session_state.get('auth_proof')
    if not session_valid(role, proof, admin_password, viewer_password):
        st.session_state.pop('auth_role', None)
        st.session_state.pop('auth_proof', None)
        st.title('🔒 A-Team · Anmeldung')
        st.info('Administratoren verwalten Daten. Zuschauer können Ergebnisse und Entwicklungen ansehen.')
        with st.form('role_login_form'):
            entered = st.text_input('Zugangspasswort', type='password')
            submitted = st.form_submit_button('Anmelden', type='primary')
        if submitted:
            matched = authenticate(entered, admin_password, viewer_password)
            if matched is not None:
                st.session_state['auth_role'] = matched
                st.session_state['auth_proof'] = session_proof(matched, admin_password, viewer_password)
                st.rerun()
            else:
                st.error('Das Passwort ist nicht korrekt.')
        st.stop()
else:
    # The local SQLite installation remains an offline administrator tool.
    role = 'admin'


def is_admin() -> bool:
    return can_edit(role)


def require_admin():
    """Server-side check for privileged routes (not merely hidden navigation)."""
    if not is_admin():
        st.error('Diese Funktion ist nur für Administratoren verfügbar.')
        st.stop()

import database as db
from csv_import import read_csv
from domain import ATTEMPTS, format_attempt
from relativwertung import relativwerte, mit_relativwerten

# Database tables only need to be initialized once per Streamlit server process.
# Streamlit reruns the script on every widget interaction; repeating DDL and a
# new Neon connection on each rerun needlessly slows the UI down.
@st.cache_resource(show_spinner=False)
def _ensure_database_initialized():
    db.init_db()
    return True

_ensure_database_initialized()

COLORS = {'total_kg':'#35d4bd','snatch_best':'#67aaff','clean_jerk_best':'#f7bd66', 'bodyweight_kg':'#b7a4ff', 'relative_points':'#efbb66'}
METRICS = {'total_kg':'Zweikampf','snatch_best':'Reißen','clean_jerk_best':'Stoßen','bodyweight_kg':'Körpergewicht', 'relative_points':'Relativpunkte'}
GENDERS = {'-':'Keine Angabe','w':'Weiblich','m':'Männlich','d':'Divers'}

st.markdown('''<style>
.block-container {padding-top: 2rem; padding-bottom: 4rem; max-width: 1450px}
[data-testid="stSidebar"] {border-right: 1px solid #25364a}
.hero {padding: 28px 32px; border: 1px solid #244055; border-radius: 18px;
background: linear-gradient(110deg, #113039 0%, #112139 70%, #111d30 100%); margin-bottom: 25px}
.hero h1 {font-size: 2.2rem; margin: 0 0 .2rem; letter-spacing: -.03em}
.hero p {color:#9bb7c4; margin: 0; font-size: 1.02rem}
.eyebrow {color:#35d4bd; letter-spacing: .12em; font-size: .78rem; font-weight:800; margin-bottom: 9px}
[data-testid="stMetric"] {background: #17263a; border: 1px solid #263a50; border-radius: 14px; padding: 18px}
[data-testid="stMetricLabel"] {color:#a9becb}
.page-subtitle {color:#a6b6c7;margin-top:-8px;margin-bottom:24px}
div.stButton>button[kind="primary"] {font-weight:700}
.small-note {font-size:.86rem;color:#a6b6c7}
</style>''', unsafe_allow_html=True)


def heading(label: str, subtitle: str=''):
    st.markdown(f'<div class="eyebrow">VEREINSTRAINING · WETTKAMPFDATEN</div>', unsafe_allow_html=True)
    st.title(label)
    if subtitle:
        st.markdown(f'<div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


@st.cache_data(ttl=5, max_entries=1, show_spinner=False)
def data():
    """Briefly cache UI lists so a tab change does not reconnect to Neon.

    After successful writes we clear this cache explicitly. Other authorized
    sessions can see each other's changes at most ~5 seconds later.
    """
    if db.IS_POSTGRES:
        athletes, comps, results = db.load_all()
    else:
        athletes = db.list_athletes()
        comps = db.list_competitions()
        results = db.list_results()
    return athletes, comps, mit_relativwerten(results)


def invalidate_data_cache():
    """Make inserts/updates/deletes immediately visible on the next rerun."""
    data.clear()


def athlete_label(a):
    return f'{a["first_name"]} {a["last_name"]}  ·  #{a["id"]}'


def comp_label(c):
    return f'{showdate(c["event_date"])} · {c["name"]}' + (f' · {c["location"]}' if c['location'] else '')


def result_label(r):
    return f'{showdate(r["event_date"])} · {r["first_name"]} {r["last_name"]} · {r["competition_name"]}  (#{r["id"]})'


def showdate(d):
    try:
        return datetime.strptime(str(d), '%Y-%m-%d').strftime('%d.%m.%Y')
    except ValueError:
        return str(d)


def kg(v, default='–'):
    if v is None or pd.isna(v):
        return default
    return f'{v:g} kg'.replace('.', ',')


def display_results(rows, *, show_athlete=True, height=340):
    if not rows:
        st.info('Noch keine Ergebnisse vorhanden.')
        return
    frame = pd.DataFrame(rows)
    cols = ['event_date', 'competition_name']
    if show_athlete:
        frame['Athlet'] = frame['first_name'] + ' ' + frame['last_name']
        cols += ['Athlet']
    cols += ['bodyweight_kg','snatch_best','clean_jerk_best','total_kg']
    # Einzelversuche kompakt sichtbar machen: 92 / x94 / 94.
    if any(any(record.get(a) is not None for a in ATTEMPTS) for record in rows):
        for prefix, title in (('s', 'Reißen: Versuche'), ('c', 'Stoßen: Versuche')):
            frame[title] = frame.apply(
                lambda record: ' / '.join(format_attempt(record[f'{prefix}{i}']) for i in range(1, 4)),
                axis=1,
            )
            cols.append(title)
    cols += ['relative_deduction','relative_snatch','relative_cj','relative_points','placing']
    view = frame[cols].rename(columns={
        'event_date':'Datum','competition_name':'Wettkampf',
        'bodyweight_kg':'Körpergewicht (kg)','snatch_best':'Reißen (kg)',
        'clean_jerk_best':'Stoßen (kg)','total_kg':'Zweikampf (kg)',
        'relative_deduction':'Relativabzug (kg)', 'relative_snatch':'Reißen (Rel.)',
        'relative_cj':'Stoßen (Rel.)','relative_points':'Relativpunkte','placing':'Platz'})
    view['Datum'] = view['Datum'].map(showdate)
    st.dataframe(view.iloc[::-1], hide_index=True, use_container_width=True, height=height)


def make_trend(rows, metric='total_kg', *, pb=True):
    df = pd.DataFrame(rows)
    if df.empty:
        return None
    df = df[df[metric].notna()].copy()
    if df.empty:
        return None
    df['x'] = pd.to_datetime(df['event_date'])
    df = df.sort_values(['x', 'id'])
    fig = go.Figure()
    unit = 'Pkt.' if metric == 'relative_points' else 'kg'
    fig.add_trace(go.Scatter(x=df['x'], y=df[metric], mode='lines+markers',
        name=METRICS[metric], marker=dict(size=10), line=dict(color=COLORS[metric], width=3),
        customdata=df[['competition_name','location']].fillna('').values,
        hovertemplate=f'%{{x|%d.%m.%Y}}<br><b>%{{y:g}} {unit}</b><br>%{{customdata[0]}}<br>%{{customdata[1]}}<extra></extra>'))
    if pb and metric != 'bodyweight_kg':
        df['previous_pb'] = df[metric].cummax().shift(1).fillna(-1)
        personal_bests = df[(df[metric] > df['previous_pb']) & (df[metric] > 0)]
        fig.add_trace(go.Scatter(x=personal_bests['x'], y=personal_bests[metric],
            mode='markers', name='Neuer Wettkampf-PB', marker=dict(color='#ffca79', size=14, symbol='star'),
            hovertemplate=f'Neuer PB: %{{y:g}} {unit}<extra></extra>'))
    fig.update_layout(height=370, margin=dict(l=5,r=10,t=15,b=10),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      font=dict(color='#d0dae5'), hovermode='x unified', legend=dict(orientation='h',y=-.18),
                      xaxis=dict(title=None, gridcolor='#253449'),
                      yaxis=dict(title='Relativpunkte' if metric == 'relative_points' else 'Kilogramm', gridcolor='#253449'))
    return fig


def stat_max(rows, field):
    candidates = [r[field] for r in rows if r.get(field) is not None and r[field] > 0]
    return max(candidates) if candidates else None


def page_overview():
    a,c,r = data()
    st.markdown('''<div class="hero"><div class="eyebrow">DAS COCKPIT FÜR DEINEN VEREIN</div>
      <h1>Jeder Versuch. Jeder Fortschritt.</h1>
      <p>Wettkämpfe dokumentieren, persönliche Bestleistungen erkennen und Entwicklungen sichtbar machen.</p></div>''',
      unsafe_allow_html=True)
    v1,v2,v3,v4 = st.columns(4)
    v1.metric('Athleten', len(a))
    v2.metric('Wettkämpfe', len(c))
    v3.metric('Wettkampfstarts', len(r))
    v4.metric('Zweikampf-Ergebnisse', sum(x['total_kg'] is not None and x['total_kg'] > 0 for x in r))
    left,right = st.columns([1.6,1], gap='large')
    with left:
        st.subheader('Letzte Ergebnisse')
        display_results(r[-6:], height=310)
    with right:
        st.subheader('Aktivste Athleten')
        if not r:
            st.info('Nach dem ersten CSV-Import erscheinen hier Auswertungen.')
        else:
            summary = pd.DataFrame(r)
            summary['Athlet'] = summary['first_name'] + ' ' + summary['last_name']
            top = summary.groupby(['athlete_id','Athlet'],as_index=False).agg(Starts=('id','count')).nlargest(6, 'Starts')
            fig = px.bar(top.sort_values('Starts'), x='Starts',y='Athlet',orientation='h',
                         color_discrete_sequence=['#35d4bd'])
            fig.update_layout(height=310, paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
                              font=dict(color='#d0dae5'), margin=dict(l=0,r=10,t=5,b=0),
                              xaxis=dict(dtick=1,gridcolor='#26384f'),yaxis=dict(title=None))
            st.plotly_chart(fig, use_container_width=True)
    st.subheader('Schnellstart')
    if is_admin():
        st.info('Links **Athleten** zum Anlegen wählen oder unter **CSV-Import** deine bestehenden Wettkampflisten einlesen.')
    else:
        st.info('Unter **Athleten** findest du die Karriereverläufe und unter **Wettkämpfe** alle Ergebnisse.')


def page_athletes():
    athletes,_,results = data()
    heading('Athleten', 'Personen verwalten, Bestleistungen ansehen und die Karriere verfolgen.' if is_admin()
            else 'Athletenprofile, Bestleistungen und Karriereverläufe ansehen.')
    if is_admin():
        create_tab,profile_tab = st.tabs(['➕ Neuen Athleten anlegen', '📈 Profil & Verwaltung'])
    else:
        profile_tab = st.container()
    if is_admin():
        with create_tab:
            with st.form('new_athlete', clear_on_submit=True):
                a1,a2 = st.columns(2)
                first = a1.text_input('Vorname *')
                last = a2.text_input('Nachname *')
                a3,a4 = st.columns(2)
                gender = a3.selectbox('Geschlecht (optional)',list(GENDERS),format_func=lambda x:GENDERS[x])
                year = a4.text_input('Geburtsjahr (optional)', placeholder='z. B. 2004')
                notes = st.text_area('Notizen (optional)',height=80)
                submitted = st.form_submit_button('Athlet anlegen',type='primary')
                if submitted:
                    try:
                        new_id = db.add_athlete(first,last,gender,year or None,notes)
                        invalidate_data_cache()
                        st.success(f'Athlet wurde angelegt (ID {new_id}).')
                        st.rerun()
                    except ValueError as ex:
                        st.error(str(ex))
    with profile_tab:
        if not athletes:
            st.info('Noch keine Athleten vorhanden.' if not is_admin() else
                    'Lege zuerst einen Athleten an oder importiere eine CSV-Datei.')
            return
        by_id = {a['id']: a for a in athletes}
        chosen = st.selectbox('Athlet auswählen', list(by_id), format_func=lambda x: athlete_label(by_id[x]),
                              key='athlete_profile')
        athlete = by_id[chosen]
        athlete_results = [r for r in results if r['athlete_id'] == chosen]
        q1,q2,q3,q4 = st.columns(4)
        q1.metric('Wettkampfstarts',len(athlete_results))
        q2.metric('PB Reißen',kg(stat_max(athlete_results,'snatch_best')))
        q3.metric('PB Stoßen',kg(stat_max(athlete_results,'clean_jerk_best')))
        q4.metric('PB Zweikampf',kg(stat_max(athlete_results,'total_kg')))
        if athlete_results and athlete['gender'] not in ('m','w'):
            st.info('Für die normale BVDG-Relativwertung bitte in den Stammdaten „Männlich“ oder „Weiblich“ festlegen.')
        if athlete_results:
            rel_pb = stat_max(athlete_results,'relative_points')
            st.metric('Persönliche Bestleistung Relativwertung',
                      f'{rel_pb:g} Punkte'.replace('.', ',') if rel_pb is not None else '–')
            valid_totals = [rec for rec in athlete_results if rec['total_kg'] is not None and rec['total_kg'] > 0]
            if len(valid_totals) >= 2:
                first_total, latest_total = valid_totals[0]['total_kg'], valid_totals[-1]['total_kg']
                improvement = latest_total - first_total
                st.metric('Entwicklung Zweikampf (erster → letzter Wettkampf)',
                          kg(latest_total), delta=f'{improvement:+g} kg seit {showdate(valid_totals[0]["event_date"])}')
            metric = st.selectbox('Leistungsverlauf', ['total_kg','snatch_best','clean_jerk_best','relative_points','bodyweight_kg'],
                                  format_func=lambda x:METRICS[x], key='athlete_graph')
            fig = make_trend(athlete_results,metric)
            if fig:
                st.plotly_chart(fig,use_container_width=True)
            st.subheader('Saisonbestleistungen')
            seasons = pd.DataFrame(athlete_results)
            seasons['Jahr'] = seasons['event_date'].str.slice(0, 4)
            summary = seasons.groupby('Jahr', as_index=False).agg(
                Starts=('id','count'), **{'Reißen PB (kg)':('snatch_best','max'),
                                      'Stoßen PB (kg)':('clean_jerk_best','max'),
                                      'Zweikampf PB (kg)':('total_kg','max'),
                                      'Relativ-PB (Pkt.)':('relative_points','max')})
            st.dataframe(summary.sort_values('Jahr', ascending=False),hide_index=True,use_container_width=True)
            st.subheader('Alle Wettkampfergebnisse')
            display_results(athlete_results,show_athlete=False)
        else:
            st.info('Noch keine Wettkampfergebnisse für diese Person.')
        if not is_admin():
            return  # Profile is read-only for spectators, including no edit/delete controls.
        with st.expander('✏️ Stammdaten bearbeiten'):
            with st.form(f'edit_athlete_{chosen}'):
                l,r = st.columns(2)
                firstname = l.text_input('Vorname',value=athlete['first_name'])
                lastname = r.text_input('Nachname',value=athlete['last_name'])
                l,r = st.columns(2)
                g = l.selectbox('Geschlecht',list(GENDERS),index=list(GENDERS).index(athlete['gender']),
                                format_func=lambda x:GENDERS[x])
                y = r.text_input('Geburtsjahr',value=str(athlete['birth_year'] or ''))
                active = st.checkbox('Aktiv',value=bool(athlete['active']))
                note = st.text_area('Notizen',value=athlete['notes'])
                if st.form_submit_button('Änderungen speichern',type='primary'):
                    try:
                        db.edit_athlete(chosen,firstname,lastname,g,y or None,note,active)
                        invalidate_data_cache()
                        st.success('Athlet gespeichert.')
                        st.rerun()
                    except ValueError as ex:
                        st.error(str(ex))
        with st.expander('🗑️ Athleten dauerhaft löschen'):
            st.warning(f'Das Löschen entfernt auch alle {len(athlete_results)} zugehörigen Wettkampfergebnisse. ' 
                       'Diese Aktion ist nicht rückgängig zu machen. Vorher am besten Datenbank sichern.')
            required = f'{athlete["first_name"]} {athlete["last_name"]}'
            confirm = st.text_input(f'Zur Bestätigung exakt „{required}“ eingeben',key=f'delete_athlete_{chosen}')
            if st.button('Athlet und sämtliche Ergebnisse löschen', type='primary',
                         disabled=(confirm != required), key='delath_button'):
                db.delete_athlete(chosen)
                invalidate_data_cache()
                st.success('Athlet und Ergebnisse gelöscht.')
                st.rerun()


def _result_form_fields(*, prefix='', initial=None, detailed=False):
    initial = initial or {}
    one,two,three = st.columns(3)
    bodyweight = one.number_input('Körpergewicht (kg)', min_value=0.0,max_value=400.0,step=0.1,
                                  value=float(initial.get('bodyweight_kg') or 0.0), key=f'{prefix}bw')
    weight_class = two.text_input('Gewichtsklasse (optional)',value=initial.get('weight_class') or '',
                                  placeholder='z. B. -81', key=f'{prefix}class')
    placing = three.number_input('Platz (0 = unbekannt)',min_value=0,max_value=999,step=1,
                                 value=int(initial.get('placing') or 0),key=f'{prefix}placing')
    fields = {}
    if detailed:
        st.caption('Pro Versuch direkt eintragen: **94** = gültig · **x94** oder **-94** = ungültig · '
                   '**v** = Verzicht · **-** = nicht angetreten. '
                   'Ein verpasster Versuch nach Ablauf der Zeit ist ungültig, nicht „-“.')
        for p, label in (('s', 'Reißen'), ('c', 'Stoßen')):
            st.markdown(f'**{label}**')
            cs = st.columns(3)
            for n, col in enumerate(cs, start=1):
                field = f'{p}{n}'
                fields[field] = col.text_input(
                    f'{n}. Versuch',
                    value=format_attempt(initial.get(field), blank='-'),
                    key=f'{prefix}{field}',
                    placeholder='94 / x94 / -94 / v / -',
                )
    else:
        l,r = st.columns(2)
        fields['snatch_best'] = l.number_input('Bestes Reißen (kg)',0.0,500.0,
            value=float(initial.get('snatch_best') or 0.0),step=1.0,key=f'{prefix}snatch') or None
        fields['clean_jerk_best'] = r.number_input('Bestes Stoßen (kg)',0.0,500.0,
            value=float(initial.get('clean_jerk_best') or 0.0),step=1.0,key=f'{prefix}cleanjerk') or None
    notes = st.text_area('Bemerkung (optional)', value=initial.get('notes') or '',key=f'{prefix}notes', height=70)
    return {**fields,'bodyweight_kg':bodyweight or None,'weight_class':weight_class,
            'placing':placing or None,'notes':notes}


def page_competitions_viewer():
    """Read-only competition directory and results for authenticated spectators."""
    _, competitions, results = data()
    heading('Wettkämpfe', 'Wettkampfergebnisse ansehen – ohne Bearbeitungsrechte.')
    if not competitions:
        st.info('Noch keine Wettkämpfe vorhanden.')
        return
    comp_df = pd.DataFrame(competitions)
    comp_df['Datum'] = comp_df['event_date'].map(showdate)
    st.dataframe(comp_df[['Datum','name','location','starts']].rename(
        columns={'name':'Wettkampf','location':'Ort','starts':'Starts'}),
        hide_index=True, use_container_width=True)
    by_id = {c['id']: c for c in competitions}
    selection = st.selectbox('Wettkampf auswählen',
        [0] + list(by_id),
        format_func=lambda value: 'Alle Wettkämpfe' if value == 0 else comp_label(by_id[value]))
    filtered = results if selection == 0 else [r for r in results if r['competition_id'] == selection]
    display_results(filtered)


def page_competitions():
    if not is_admin():
        return page_competitions_viewer()
    athletes, competitions, results = data()
    heading('Wettkämpfe', 'Veranstaltungen und Starts manuell erfassen oder bestehende Ergebnisse korrigieren.')
    tab1,tab2,tab3 = st.tabs(['➕ Ergebnis erfassen','🏟️ Wettkämpfe verwalten','📝 Ergebnisse verwalten'])
    with tab1:
        if not athletes:
            st.warning('Bitte zuerst einen Athleten unter „Athleten“ anlegen.')
        else:
            athlete_map = {a['id']:a for a in athletes}
            comp_map = {c['id']:c for c in competitions}
            detailed = st.checkbox('Einzelversuche erfassen (inkl. x94, -94, v, -)', value=True, key='manual_detailed')
            st.caption('Die BVDG-Relativpunkte berechnet die App nach dem Speichern automatisch aus Geschlecht, Körpergewicht und gültigen Bestwerten. Kein zusätzliches Punktefeld nötig.')
            with st.form('add_result'):
                aid = st.selectbox('Athlet',list(athlete_map),format_func=lambda v:athlete_label(athlete_map[v]))
                options = [0]+list(comp_map)
                cid = st.selectbox('Wettkampf',options,format_func=lambda v:'➕ Neuen Wettkampf anlegen' if v==0 else comp_label(comp_map[v]))
                if cid==0:
                    name = st.text_input('Name des Wettkampfs *',placeholder='z. B. Bezirksmeisterschaft')
                    l,r = st.columns(2)
                    event_date = l.date_input('Wettkampfdatum',value=date.today(),format='DD.MM.YYYY')
                    location = r.text_input('Ort (optional)')
                else:
                    name = event_date = location = None
                result = _result_form_fields(prefix='new',detailed=detailed)
                submit = st.form_submit_button('Ergebnis speichern',type='primary')
                if submit:
                    try:
                        # Form validity checked before new competition is created.
                        from domain import validate_result
                        validate_result(result)
                        if cid==0:
                            from domain import safe_name
                            safe_name(name, 'Wettkampf')
                            cid = db.create_competition(name,event_date,location)
                            invalidate_data_cache()
                        status = db.save_result(aid,cid,result,overwrite=False)
                        invalidate_data_cache()
                        if status=='übersprungen':
                            st.warning('Für diese Person existiert bei diesem Wettkampf bereits ein Ergebnis. ' 
                                       'Zum Korrigieren den Tab „Ergebnisse verwalten“ verwenden.')
                        else:
                            calculated = relativwerte({**result, 'gender': athlete_map[aid]['gender'],
                                                       **validate_result(result)})
                            points = calculated['relative_points']
                            if points is not None:
                                st.success(f'Ergebnis gespeichert · {points:g} Relativpunkte automatisch berechnet.')
                            else:
                                st.success('Ergebnis gespeichert. Für Relativpunkte sind gültige Leistungen, Geschlecht und ein Körpergewicht innerhalb der Tabelle nötig.')
                    except ValueError as ex:
                        st.error(str(ex))
    with tab2:
        with st.form('create_competition',clear_on_submit=True):
            st.markdown('**Neuen Wettkampf ohne Ergebnis anlegen**')
            comp_name = st.text_input('Wettkampfbezeichnung')
            l,r = st.columns(2)
            comp_date = l.date_input('Datum',value=date.today(),format='DD.MM.YYYY',key='comp_date')
            comp_loc = r.text_input('Ort',key='comp_loc')
            if st.form_submit_button('Wettkampf anlegen',type='primary'):
                try:
                    db.create_competition(comp_name,comp_date,comp_loc)
                    invalidate_data_cache()
                    st.success('Wettkampf angelegt.')
                    st.rerun()
                except ValueError as ex:
                    st.error(str(ex))
        st.subheader('Alle Wettkämpfe')
        if competitions:
            comp_df = pd.DataFrame(competitions)
            comp_df['Datum'] = comp_df['event_date'].map(showdate)
            st.dataframe(comp_df[['Datum','name','location','starts']].rename(
                columns={'name':'Wettkampf','location':'Ort','starts':'Starts'}),hide_index=True,use_container_width=True)
            with st.expander('Wettkampf löschen'):
                c_map={c['id']:c for c in competitions}
                delcid=st.selectbox('Wettkampf auswählen',list(c_map),format_func=lambda v:comp_label(c_map[v]))
                st.warning('Dabei werden sämtliche Ergebnisse dieses Wettkampfs gelöscht.')
                confirm=st.checkbox('Ich möchte den Wettkampf und alle seine Ergebnisse endgültig löschen.')
                if st.button('Wettkampf löschen',disabled=not confirm):
                    db.delete_competition(delcid)
                    invalidate_data_cache()
                    st.success('Wettkampf gelöscht.')
                    st.rerun()
        else:
            st.info('Noch keine Wettkämpfe angelegt.')
    with tab3:
        if not results:
            st.info('Noch keine Ergebnisse vorhanden.')
        else:
            display_results(results)
            map_results = {r['id']:r for r in results[::-1]}
            rid = st.selectbox('Ergebnis zum Bearbeiten wählen',list(map_results),
                               format_func=lambda v:result_label(map_results[v]))
            selected=map_results[rid]
            has_attempts = any(selected.get(attempt) is not None for attempt in ATTEMPTS)
            detailed_edit = st.checkbox(
                'Einzelversuche bearbeiten (inklusive Verzicht / Nichtantritt)',
                value=has_attempts, key=f'edit_detailed_{rid}',
            )
            if has_attempts and not detailed_edit:
                st.warning('Achtung: Beim Speichern als Bestwerte werden die sechs bisherigen Einzelversuche entfernt.')
            with st.form(f'edit_result_{rid}'):
                changes = _result_form_fields(prefix=f'edit_{rid}_', initial=selected, detailed=detailed_edit)
                if st.form_submit_button('Ergebnis aktualisieren',type='primary'):
                    try:
                        state=db.save_result(selected['athlete_id'],selected['competition_id'],changes,overwrite=True)
                        invalidate_data_cache()
                        st.success('Ergebnis aktualisiert.')
                        st.rerun()
                    except ValueError as ex:
                        st.error(str(ex))
            with st.expander('Ergebnis löschen'):
                checked=st.checkbox('Ja, dieses einzelne Ergebnis unwiderruflich löschen.',key=f'confirm_delres_{rid}')
                if st.button('Ergebnis löschen',disabled=not checked,key=f'delres_{rid}'):
                    db.delete_result(rid)
                    invalidate_data_cache()
                    st.success('Ergebnis gelöscht.')
                    st.rerun()


def _csv_export(results):
    columns = ['athleten_id','Vorname','Nachname','Geschlecht','Datum','Wettkampf','Ort',
        'Körpergewicht','Gewichtsklasse','Reißen','Stoßen','Zweikampf','Relativabzug','Relativ Reißen','Relativ Stoßen','Relativpunkte','Platz','Bemerkung',
        's1','s2','s3','c1','c2','c3']
    buffer = StringIO()
    writer=csv.DictWriter(buffer,fieldnames=columns,delimiter=';',lineterminator='\r\n')
    writer.writeheader()
    for r in results:
        values = {'athleten_id':r['athlete_id'], 'Vorname':r['first_name'], 'Nachname':r['last_name'],
            'Geschlecht':r['gender'],'Datum':r['event_date'],'Wettkampf':r['competition_name'],'Ort':r['location'],
            'Körpergewicht':r['bodyweight_kg'],'Gewichtsklasse':r['weight_class'],
            'Reißen':r['snatch_best'],'Stoßen':r['clean_jerk_best'],'Zweikampf':r['total_kg'],
            'Relativabzug':r['relative_deduction'],'Relativ Reißen':r['relative_snatch'],
            'Relativ Stoßen':r['relative_cj'],'Relativpunkte':r['relative_points'],
            'Platz':r['placing'],'Bemerkung':r['notes'],
            **{attempt: format_attempt(r[attempt], blank='-') for attempt in ATTEMPTS}}
        writer.writerow({k: ('' if v is None else str(v).replace('.',',') if isinstance(v,float) else v)
                         for k,v in values.items()})
    return buffer.getvalue().encode('utf-8-sig')


def page_csv():
    require_admin()
    heading('CSV-Import','Wettkämpfe aus vorhandenen Listen übernehmen – auch mehrere Athleten gleichzeitig.')
    example_path=db.BASE / 'beispiele' / 'wettkaempfe_beispiel.csv'
    l,r=st.columns(2)
    l.download_button('⬇️ Beispiel-CSV herunterladen',example_path.read_bytes(),
                      file_name='wettkaempfe_beispiel.csv',mime='text/csv')
    advanced=db.BASE / 'beispiele' / 'versuchsstatus_beispiel.csv'
    r.download_button('⬇️ Beispiel mit Einzelversuchen',advanced.read_bytes(),
                      file_name='versuchsstatus_beispiel.csv',mime='text/csv')
    st.info('Pflicht: **Athlet** (oder **Vorname** + **Nachname**), **Datum**, **Wettkampf** und '
            'mindestens ein Ergebnis oder dokumentierter Versuch (auch **v** oder ungültig). '
            'Gültig: **94**, ungültig: **x94** oder **-94**, Verzicht: **v**, '
            'nicht angetreten: **-**. Ein Zweikampf wird nur bei gültigem Reißen '
            'und Stoßen berechnet. Neue Athleten und Wettkämpfe werden automatisch angelegt.')
    upload=st.file_uploader('CSV-Datei auswählen',type=['csv'])
    if upload is None:
        st.caption('Erlaubt: CSV mit Semikolon, Komma oder Tab als Trennzeichen; UTF-8 oder Windows-1252.')
        return
    try:
        parsed,errors,metadata=read_csv(upload.getvalue())
    except ValueError as ex:
        st.error(str(ex))
        return
    s1,s2,s3=st.columns(3)
    s1.metric('Importierbare Zeilen',len(parsed))
    s2.metric('Fehlerhafte Zeilen',len(errors))
    s3.metric('Erkannte Spalten',len(metadata['columns']))
    if errors:
        with st.expander(f'⚠️ Importfehler ({len(errors)})',expanded=True):
            for error in errors[:100]:
                st.error(error)
            if len(errors)>100:
                st.caption(f'{len(errors)-100} weitere Fehler nicht angezeigt.')
    if not parsed:
        st.warning('Keine gültigen Ergebnisse zum Import gefunden.')
        return
    st.subheader('Vorschau')
    preview_records = [{**row, **relativwerte(row)} for row in parsed]
    preview = pd.DataFrame(preview_records)
    wanted = ['first_name','last_name','competition_name','event_date','bodyweight_kg',
              'snatch_best','clean_jerk_best','total_kg','relative_deduction','relative_points']
    if any(any(row.get(a) is not None for a in ATTEMPTS) for row in parsed):
        for prefix, title in (('s', 'Reißen: Versuche'), ('c', 'Stoßen: Versuche')):
            preview[title] = preview.apply(
                lambda row: ' / '.join(format_attempt(row[f'{prefix}{i}']) for i in range(1, 4)), axis=1,
            )
            wanted.append(title)
    st.dataframe(preview[[k for k in wanted if k in preview]].head(30),hide_index=True,use_container_width=True)
    st.caption('Relativpunkte in der Vorschau benötigen Geschlecht und Körpergewicht in der CSV. ' 
               'Für bereits angelegte Athleten wird nach dem Import das Geschlecht aus dem Athletenprofil verwendet.')
    replace=st.checkbox('Bereits vorhandene Ergebnisse (Athlet + Wettkampf) überschreiben',value=False)
    st.caption('Ohne Häkchen werden Doppeleinträge übersprungen. Fehlerhafte Zeilen werden nicht importiert.')
    if st.button(f'{len(parsed)} Ergebnisse importieren',type='primary'):
        try:
            stats=db.import_results(parsed,overwrite=replace)
            invalidate_data_cache()
            st.success(f'Import abgeschlossen: {stats["neu"]} neu, {stats["aktualisiert"]} aktualisiert, '
                f'{stats["übersprungen"]} übersprungen. Neue Athleten: {stats["athleten_neu"]}; '
                f'neue Wettkämpfe: {stats["wettkaempfe_neu"]}.')
        except ValueError as ex:
            st.error(f'Import abgebrochen – keine Teiländerungen gespeichert: {ex}')


def page_analysis():
    athletes,_,results=data()
    heading('Auswertungen','Trainings- und Wettkampffortschritte auf einen Blick.')
    if not results:
        st.info('Importiere oder erfasse zuerst Wettkampfergebnisse.')
        return
    by_id={a['id']:a for a in athletes}
    l,r=st.columns([1.5,1])
    metric=l.selectbox('Wert auswählen',list(METRICS),format_func=lambda x:METRICS[x])
    chosen=r.multiselect('Athleten vergleichen',list(by_id),default=list(by_id)[:min(len(by_id),3)],
                           format_func=lambda v:athlete_label(by_id[v]),max_selections=8)
    if not chosen:
        st.warning('Bitte mindestens einen Athleten auswählen.')
        return
    frame=pd.DataFrame([rec for rec in results if rec['athlete_id'] in chosen and rec[metric] is not None])
    if frame.empty:
        st.info('Für die Auswahl gibt es noch keine Werte.')
        return
    frame['Athlet']=frame['first_name']+' '+frame['last_name']+' (#'+frame['athlete_id'].astype(str)+')'
    frame['Datum']=pd.to_datetime(frame['event_date'])
    fig=px.line(frame.sort_values('Datum'),x='Datum',y=metric,color='Athlet',markers=True,
                hover_data={'competition_name':True,'Datum':True,metric:':.1f'},
                labels={metric:f'{METRICS[metric]} ({"Pkt." if metric == "relative_points" else "kg"})'})
    fig.update_traces(line=dict(width=3),marker=dict(size=9))
    fig.update_layout(height=480,paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
                      font=dict(color='#d0dae5'),margin=dict(l=5,r=10,t=15,b=15),
                      xaxis=dict(gridcolor='#253449'),yaxis=dict(gridcolor='#253449'))
    st.plotly_chart(fig,use_container_width=True)
    st.subheader('Persönliche Bestleistungen im Wettkampf')
    records=[]
    for aid in chosen:
        records_for=[rec for rec in results if rec['athlete_id']==aid]
        records.append({'Athlet':athlete_label(by_id[aid]),'Starts':len(records_for),
            'Reißen PB (kg)':stat_max(records_for,'snatch_best'),
            'Stoßen PB (kg)':stat_max(records_for,'clean_jerk_best'),
            'Zweikampf PB (kg)':stat_max(records_for,'total_kg'),
            'Relativ-PB (Pkt.)':stat_max(records_for,'relative_points')})
    st.dataframe(pd.DataFrame(records),hide_index=True,use_container_width=True)
    st.caption('PB = persönliche Wettkampfbestleistung innerhalb der gespeicherten Daten. ' 
               'Relativpunkte nach BVDG-Abzugstabelle, ohne Altersfaktor.')


def page_backup():
    require_admin()
    _,_,results=data()
    heading('Export & Sicherung','Daten lokal sichern und für andere Programme exportieren.')
    st.subheader('Ergebnisliste als CSV')
    st.write('Alle Ergebnisse mit Athleten-IDs, Wettkämpfen, Bestwerten und Einzelversuchen. ' 
             'Diese CSV kann später wieder eingelesen werden.')
    st.download_button('⬇️ Alle Ergebnisse als CSV',_csv_export(results),
        file_name=f'gewichtheben_ergebnisse_{date.today().isoformat()}.csv',mime='text/csv',
        disabled=not results)
    st.divider()
    st.subheader('Vollständige Daten sichern')
    if db.IS_POSTGRES:
        st.write('Exportiert Athleten, Wettkämpfe und alle Ergebnisse in drei JSON-Dateien als ZIP. '
                 '**Dieser Export kann nicht direkt in der App wiederhergestellt werden.** '
                 'Für ein wiederherstellbares Datenbank-Backup die Sicherungsfunktion des PostgreSQL-Anbieters nutzen.')
        st.download_button('⬇️ Datenexport als ZIP herunterladen', db.backup_bytes(),
            file_name=f'gewichtheben_export_{date.today().isoformat()}.zip',
            mime='application/zip')
    else:
        st.write('Enthält Athletenstammdaten, Wettkämpfe und sämtliche Ergebnisse. '
                 'Bei der lokalen SQLite-Version lässt sich die Datei nach dem Beenden der App '
                 'als `data/verein.sqlite3` wiederherstellen.')
        st.download_button('⬇️ SQLite-Datenbank herunterladen', db.backup_bytes(),
            file_name=f'gewichtheben_backup_{date.today().isoformat()}.sqlite3',
            mime='application/octet-stream')
    st.warning('Exporte enthalten personenbezogene Daten und müssen geschützt aufbewahrt werden.')


ADMIN_PAGES = ['🏠 Übersicht','👥 Athleten','🏟️ Wettkämpfe',
               '📥 CSV-Import','📈 Auswertungen','💾 Export & Sicherung']
VIEWER_PAGES = ['🏠 Übersicht','👥 Athleten','🏟️ Wettkämpfe','📈 Auswertungen']

with st.sidebar:
    st.markdown('## 🏋️ A-TEAM ATHLETE DB')
    st.caption('WETTKAMPF- & KARRIERE-TRACKER')
    st.divider()
    st.caption('👑 Administrator' if is_admin() else '👀 Zuschauer · nur lesen')
    page = st.radio('Navigation', ADMIN_PAGES if is_admin() else VIEWER_PAGES,
                    label_visibility='collapsed')
    st.divider()
    if db.IS_POSTGRES:
        st.caption('PostgreSQL · dauerhafte Cloud-Speicherung')
        if st.button('🔒 Abmelden'):
            st.session_state.pop('auth_role', None)
            st.session_state.pop('auth_proof', None)
            st.session_state.pop('logged_in', None)  # Legacy auth state.
            st.rerun()
    else:
        st.caption('SQLite · lokale Speicherung (auf Streamlit Cloud nicht dauerhaft)')
    st.caption('Version 1.7 · Admin- und Zuschauerrollen')

PAGES = {'🏠 Übersicht': page_overview, '👥 Athleten': page_athletes,
         '🏟️ Wettkämpfe': page_competitions, '📥 CSV-Import': page_csv,
         '📈 Auswertungen': page_analysis, '💾 Export & Sicherung': page_backup}
if page not in (ADMIN_PAGES if is_admin() else VIEWER_PAGES):
    st.error('Keine Berechtigung für diese Seite.')
    st.stop()
PAGES[page]()
