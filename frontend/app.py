import os
import uuid

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Census Chat", page_icon="📊", layout="centered")

# --- Sidebar ---
with st.sidebar:
    st.title("Census Chat")
    st.caption("Ask questions about the US population using Census data.")

    if st.button("New Conversation"):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        try:
            requests.post(
                f"{BACKEND_URL}/clear-session",
                params={"session_id": st.session_state.get("session_id", "default")},
                timeout=5,
            )
        except Exception:
            pass
        st.rerun()

    st.divider()
    st.markdown("**Backend status**")
    try:
        resp = requests.get(f"{BACKEND_URL}/health", timeout=5)
        health = resp.json()
        st.write(f"Snowflake: {health.get('snowflake', 'unknown')}")
        st.write(f"Gemini: {health.get('gemini', 'unknown')}")
        st.write(f"Embeddings: {health.get('embeddings', 'unknown')}")
        table_count = health.get("schema_tables", 0)
        if table_count:
            st.write(f"Schema: {table_count} tables indexed")
    except Exception:
        st.error("Backend unreachable")

# --- Session state init ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# --- Chat history ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sql_query"):
            with st.expander("View SQL"):
                st.code(msg["sql_query"], language="sql")

# --- User input ---
if prompt := st.chat_input("Ask about US Census data..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                resp = requests.post(
                    f"{BACKEND_URL}/chat",
                    json={
                        "message": prompt,
                        "session_id": st.session_state.session_id,
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()
                answer = data["response"]
                sql_query = data.get("sql_query")
            except requests.exceptions.ConnectionError:
                answer = "Could not connect to the backend. Please check that the server is running."
                sql_query = None
            except requests.exceptions.Timeout:
                answer = "The request timed out. Please try a simpler question."
                sql_query = None
            except Exception as e:
                answer = f"An error occurred: {e}"
                sql_query = None

        st.markdown(answer)
        if sql_query:
            with st.expander("View SQL"):
                st.code(sql_query, language="sql")

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sql_query": sql_query,
    })
