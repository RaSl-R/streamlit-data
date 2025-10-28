import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from utils.db import get_engine

# === NASTAVENÍ DB CONNECTION ===
engine = get_engine()

st.set_page_config(layout="centered")
st.title("Streamlit aplikace pro SnowPro Core certifikaci 🧊")

# --- Session state ---
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}
if "page_number" not in st.session_state:
    st.session_state.page_number = 0
if "reset_success" not in st.session_state:
    st.session_state.reset_success = False

# --- Mock autentizace (nebo jiný mechanismus) ---
def get_current_user():
    # V produkci napoj na autentizaci (např. Streamlit Cloud auth)
    return "test_user@example.com"

st.session_state.user_id = get_current_user()
st.write(f"Přihlášený uživatel: **{st.session_state.user_id}**")

# --- Načtení otázek ---
@st.cache_data
def load_data():
    with engine.connect() as conn:
        df = pd.read_sql(
            "SELECT * FROM my_schema.l2_snowpro_data_for_streamlit WHERE is_showed = 'Y'",
            conn
        )
    return df

def sanitize(value):
    if value is None:
        return ""
    return str(value).replace("'", "''")

# --- Uložení odpovědi (UPSERT) ---
def save_answer_to_db(user_id, question_id, selected_answers):
    answers = ', '.join(selected_answers)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO my_schema.l2_user_answers (user_id, question_id, answer, inserted_datetime)
            VALUES (:user_id, :question_id, :answer, NOW())
            ON CONFLICT (user_id, question_id)
            DO UPDATE SET answer = EXCLUDED.answer, inserted_datetime = NOW();
        """), {"user_id": user_id, "question_id": question_id, "answer": answers})
    st.session_state.user_answers = load_user_answers(user_id)

# --- Načtení odpovědí uživatele ---
def load_user_answers(user_id):
    with engine.connect() as conn:
        df = pd.read_sql(
            text("SELECT question_id, answer FROM my_schema.l2_user_answers WHERE user_id = :uid"),
            conn,
            params={"uid": user_id}
        )
    return {row["question_id"]: row["answer"].split(', ') for _, row in df.iterrows()}

# --- Přidání otázky do seznamu těžkých/špatných ---
def add_row_to_db(row):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO my_schema.l2_snowpro_data_hard_or_wrong_questions
            (question_id, question, answer_a, answer_b, answer_c, answer_d, answer_e, answer_f, suggested_answer, url, inserted_by)
            VALUES (:question_id, :question, :a, :b, :c, :d, :e, :f, :sugg, :url, :by)
        """), {
            "question_id": row["question_id"],
            "question": row["question"],
            "a": row["answer_a"],
            "b": row["answer_b"],
            "c": row["answer_c"],
            "d": row["answer_d"],
            "e": row.get("answer_e", ""),
            "f": row.get("answer_f", ""),
            "sugg": row["formatted_suggested_answer"],
            "url": row["url"],
            "by": st.session_state.user_id
        })
    st.success("Otázka byla přidána mezi těžké/špatné!")

# --- Reset všech odpovědí ---
def reset_all_answers(user_id):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM my_schema.l2_user_answers WHERE user_id = :uid"), {"uid": user_id})
    st.session_state.user_answers = {}
    st.session_state.reset_success = True

# --- Zobrazení otázek ---
def show_questions(current_data, user_answers):
    for _, row in current_data.iterrows():
        qid = row["question_id"]
        question = row["question"]

        st.markdown(f"**Question {qid}:** {question}")
        selected = user_answers.get(qid, [])
        choices = []

        for label in ["A", "B", "C", "D", "E", "F"]:
            ans = row.get(f"answer_{label.lower()}")
            if ans and str(ans).strip():
                if st.checkbox(ans, key=f"{qid}_{label}", value=(label in selected)):
                    choices.append(label)

        if set(choices) != set(selected):
            if choices:
                save_answer_to_db(st.session_state.user_id, qid, choices)
            else:
                with engine.begin() as conn:
                    conn.execute(text("""
                        DELETE FROM my_schema.l2_user_answers 
                        WHERE user_id = :uid AND question_id = :qid
                    """), {"uid": st.session_state.user_id, "qid": qid})
                st.session_state.user_answers = load_user_answers(st.session_state.user_id)

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("SHOW ANSWER", key=f"show_{qid}"):
                correct = [x.strip() for x in row["formatted_suggested_answer"].split(",")]
                if sorted(choices) == sorted(correct):
                    st.success("Správně! ✅")
                else:
                    st.error("Špatně ❌")
                    st.info(f"Správná odpověď: {', '.join(correct)}")
                    st.write(f"Odkaz: {row['url']}")
        with col2:
            if st.button("Hard / Wrong", key=f"flag_{qid}"):
                add_row_to_db(row)
        with col3:
            st.link_button("🔍 Otevřít otázku", row["url"])

# --- Logika stránkování ---
data = load_data()
questions_per_page = 10
total_pages = (len(data) - 1) // questions_per_page + 1

st.write(f"Stránka {st.session_state.page_number + 1} / {total_pages}")

start = st.session_state.page_number * questions_per_page
end = start + questions_per_page
current = data.iloc[start:end]
user_answers = load_user_answers(st.session_state.user_id)

show_questions(current, user_answers)

col1, _, col3 = st.columns([1, 2, 1])
if col1.button("Previous") and st.session_state.page_number > 0:
    st.session_state.page_number -= 1
    st.rerun()
if col3.button("Next") and st.session_state.page_number < total_pages - 1:
    st.session_state.page_number += 1
    st.rerun()

# --- Reset odpovědí ---
if st.button("Reset all answers"):
    reset_all_answers(st.session_state.user_id)
    st.rerun()

if st.session_state.reset_success:
    st.success("Všechny odpovědi resetovány!")
    st.session_state.reset_success = False

answered = len(st.session_state.user_answers)
st.write(f"Odpověděl jsi na {answered} z {len(data)} otázek.")
