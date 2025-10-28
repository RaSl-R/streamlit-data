import streamlit as st
import psycopg2
from sqlalchemy import create_engine

DB_USER = st.secrets["DB_USER"]
DB_PASSWORD = st.secrets["DB_PASSWORD"]
DB_HOST = st.secrets["DB_HOST"]
DB_NAME = st.secrets["DB_NAME"]

@st.cache_resource
def get_engine():
    conn_str = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
    return create_engine(conn_str, connect_args={"sslmode": "require"})

@st.cache_resource
def get_connection():
    return get_engine().connect()
