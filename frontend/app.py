import json
import os

import requests
import streamlit as st

CONTROL_PLANE = os.getenv(
    "CONTROL_PLANE_URL",
    "http://control-plane:7000",
)

API_KEY = os.getenv(
    "CONTROL_PLANE_API_KEY",
    "devkey-change-me",
)

HEADERS = {
    "X-API-Key": API_KEY
}


def refresh():
    requests.post(
        f"{CONTROL_PLANE}/refresh",
        headers=HEADERS,
    )


def health():
    requests.post(
        f"{CONTROL_PLANE}/health-check",
        headers=HEADERS,
    )


def load_agents():
    r = requests.get(
        f"{CONTROL_PLANE}/agents",
        headers=HEADERS,
    )
    r.raise_for_status()
    return r.json()["agents"]


def call(agent, text):

    payload = {
        "agent_name": agent,
        "input_data": text
    }

    r = requests.post(
        f"{CONTROL_PLANE}/call",
        json=payload,
        headers=HEADERS,
    )

    r.raise_for_status()

    return r.json()


st.set_page_config(
    page_title="A2A Control Plane",
    layout="wide",
)

st.title("A2A Control Plane")

col1, col2 = st.columns(2)

with col1:
    if st.button("Refresh Discovery"):
        refresh()
        st.success("Discovery executed")

with col2:
    if st.button("Health Check"):
        health()
        st.success("Health check executed")

st.divider()

agents = load_agents()

st.header(f"Agents ({len(agents)})")

for agent in agents:

    with st.expander(agent["name"], expanded=False):

        c1, c2 = st.columns(2)

        with c1:
            st.write("### Information")

            st.write("**URL**")
            st.code(agent["url"])

            st.write("**Description**")
            st.write(agent["description"])

            st.write("**Status**")
            st.write(agent["status"])

            st.write("**Source**")
            st.write(agent["source"])

        with c2:

            st.write("### Health")

            st.metric(
                "Failures",
                agent["health"]["total_failures"]
            )

            st.metric(
                "Successes",
                agent["health"]["total_successes"]
            )

            st.metric(
                "Consecutive failures",
                agent["health"]["consecutive_failures"]
            )

            st.metric(
                "Average latency",
                agent["latency"]["avg_ms"]
            )

        st.write("### Skills")

        for s in agent["skills"]:

            st.markdown(f"**{s['name']}**")

            st.write(s["description"])

            st.caption(", ".join(s["tags"]))

        st.divider()

        txt = st.text_input(
            "Input",
            key=agent["name"]
        )

        if st.button(
            f"Call {agent['name']}",
            key=f"call_{agent['name']}"
        ):

            result = call(agent["name"], txt)

            st.success("Response")

            st.json(result)