"""One-screen demo: pick a sample job, click Migrate, read the verdict. Offline (simulated agents)."""
import streamlit as st

from receipts.config import Settings
from receipts.pipeline import migrate
from receipts.samples.simulated import EXPECTED, SimulatedAgents, job_source

st.title("Receipts")
st.caption("Legacy job in. Verdict and verifiable receipt out. The agent never deploys.")
name = st.selectbox("Sample job", list(EXPECTED))
left, right = st.columns(2)
left.code(job_source(name), language="bash")
if left.button("Migrate"):
    res = migrate(name, job_source(name), SimulatedAgents(), Settings())
    color = {"READY FOR REVIEW": "green", "NEEDS INFO": "orange", "BLOCKED": "red"}[res.receipt.verdict.value]
    right.markdown(f"### :{color}[{res.receipt.verdict.value}]")
    for c in res.receipt.checks:
        right.write(f"**{c.name}** {c.status.value}: {c.detail}")
    for note in res.receipt.ledger:
        right.caption(f"Refused: {note}")
    right.caption(f"Receipt {res.receipt.receipt_sha256[:16]}")
