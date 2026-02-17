# -------------------------------------------------------------
#  OptiCoder — Claude-Only Qualitative Summariser (Multi-Question)
#  Last updated: 2025-05-06
# -------------------------------------------------------------

import streamlit as st
import re
import os
import json
from io import BytesIO
from datetime import datetime
from anthropic import Anthropic
import xml.etree.ElementTree as ET

# PDF support
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet
    from PIL import Image as PILImage
    pdf_supported = True
except ImportError:
    pdf_supported = False

# Config
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
MAX_CLAUDE_TOKENS = 1500
PROJECTS_FILE = "projects.json"
COST_PER_TOKEN = 0.00001  # USD per token

# Load or init projects
if os.path.exists(PROJECTS_FILE):
    with open(PROJECTS_FILE, "r") as f:
        projects = json.load(f)
else:
    projects = {}

# Session context
default_ctx = st.session_state.get("context", {})

# Initialize Claude client
client = Anthropic(api_key=st.secrets.get("ANTHROPIC_API_KEY", ""))

# Streamlit page config
st.set_page_config(page_title="Opticom's OptiCoder", layout="wide")
logo_path = os.path.join(os.path.dirname(__file__), "Opticom Logotype Blue_tagline_rgb.png")
col_logo, col_title = st.columns([1, 4])
with col_logo:
    if os.path.exists(logo_path):
        st.image(logo_path, width=150, use_container_width=False)
    else:
        st.warning("Logo not found.")
with col_title:
    st.markdown(f"""
# 🌐 OptiCoder
_Last updated: {datetime.now():%Y-%m-%d}_
""", unsafe_allow_html=True)

# Step 1: Context
with st.expander("1. Project Context", expanded=True):
    sel = st.selectbox("Load project:", ["-- New --"] + list(projects.keys()))
    project_no = sel if sel != "-- New --" else st.text_input("Project Number")
    defaults = projects.get(project_no, {}) if project_no else {}
    c1, c2 = st.columns(2)
    with c1:
        client_name = st.text_input("Client Name", value=defaults.get("client_name",""))
        industry = st.text_input("Industry", value=defaults.get("industry",""))
        resp_type = st.text_input("Respondent Type", value=defaults.get("resp_type",""))
        objectives = st.text_area("Project Objectives", value=defaults.get("objectives",""), height=80)
    with c2:
        questions_raw = st.text_area("Interview Questions (one per line)", value="\n".join(defaults.get("questions",[])), height=120)
    questions = [q.strip() for q in questions_raw.split("\n") if q.strip()]
    ctx = {"project_no": project_no, "client_name": client_name, "industry": industry,
           "resp_type": resp_type, "objectives": objectives, "questions": questions}
    st.session_state["context"] = ctx
    if project_no:
        projects[project_no] = ctx
        with open(PROJECTS_FILE, "w") as f:
            json.dump(projects, f, indent=2)

# Step 2: Responses
with st.expander("2. Paste Responses", expanded=True):
    st.markdown("One per line: `RESP_001 — answer text`.")
    raw = st.text_area("Responses", height=300, key="raw")

# Cost estimate
_tokens = max(1, len(raw or "")//4)
_cost_sek = _tokens * COST_PER_TOKEN * 10
st.info(f"🔢 Estimated tokens: {_tokens} → Cost ≈ {_cost_sek:.2f} SEK")

# Generate summaries
if st.button("📝 Generate Summaries"):
    if not raw.strip(): st.error("Paste responses."); st.stop()
    if not ctx.get("questions"): st.error("Enter at least one question."); st.stop()

    # Build prompt header with questions
    questions_list = "\n".join(f"- {q}" for q in ctx['questions'])
    header = f"""
Project: {ctx['project_no']} | Client: {ctx['client_name']} | Industry: {ctx['industry']}
Objectives: {ctx['objectives']}
Respondent Type: {ctx['resp_type']}
Questions:
{questions_list}

"""
    xml_template = """
<Summary>
  <Executive>
    <Item><![CDATA[Bullet text]]></Item>
  </Executive>
  <Narrative><![CDATA[Narrative text]]></Narrative>
  <Ideas>
    <Idea><![CDATA[Idea text]]></Idea>
  </Ideas>
  <Quotes>
    <Quote id=\"RESP_001\"><![CDATA[Quote text]]></Quote>
  </Quotes>
</Summary>
"""
    prompt = (
        header +
        "You are a senior qualitative research analyst and business strategy consultant. Generate exactly:\n"
        "- Executive Summary: 6–8 bullets, each 2–3 sentences\n"
        "- Narrative Summary: at least 400 words\n"
        "- Ideas Worth Exploring: 6–8 bullets, each 2–3 sentences\n"
        "- Top 5 Quotes: verbatim with respondent IDs\n"
        "Return only valid XML matching the template below.\n" +
        xml_template +
        f"\nRaw Responses:\n{raw}\n"
    )
  with st.spinner("Testing model…"):
    test = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=50,
        messages=[{"role": "user", "content": "Say hello"}]
    )

st.write(test.content[0].text)

    # XML parsing
    m = re.search(r"<Summary>[\s\S]*?</Summary>", response)
    if not m:
        st.error("❌ Parsing error: <Summary> missing.")
        st.text_area("Raw response", response, height=300)
        st.stop()
    xml = m.group(0)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        st.error(f"❌ XML parse error: {e}")
        st.text_area("XML", xml, height=300)
        st.stop()

    # Extract sections
    execs = [i.text or "" for i in root.find('Executive').findall('Item')]
    narrative = root.findtext('Narrative','')
    ideas = [i.text or "" for i in root.find('Ideas').findall('Idea')]
    quotes = [(q.get('id'), q.text or "") for q in root.find('Quotes').findall('Quote')]

    # Display unified boxes
    tabs = st.tabs(["Executive","Narrative","Ideas","Quotes"])
    with tabs[0]:
        exec_text = "\n".join(execs)
        st.text_area("Executive Summary", exec_text, height=200, key="exec_summary")
    with tabs[1]:
        st.text_area("Narrative Summary", narrative, height=300, key="narrative_summary")
    with tabs[2]:
        ideas_text = "\n".join(ideas)
        st.text_area("Ideas Worth Exploring", ideas_text, height=200, key="ideas_summary")
    with tabs[3]:
        for rid, txt in quotes:
            st.text_area(f"Quote {rid}", txt, height=100, disabled=False, key=f"quote_{rid}")

    # Copy expander
    with st.expander("📋 Copy Sections", expanded=False):
        st.text_area("Executive (copy)", st.session_state.exec_summary, height=200)
        st.text_area("Narrative (copy)", st.session_state.narrative_summary, height=200)
        st.text_area("Ideas (copy)", st.session_state.ideas_summary, height=200)

    # PDF export
    if pdf_supported:
        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
            leftMargin=15*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm)
        styles = getSampleStyleSheet()
        normal = styles['BodyText']
        heading = styles['Heading2']
        elems = []
        # Logo with aspect ratio
        if os.path.exists(logo_path):
            img = PILImage.open(logo_path)
            ratio = img.height/img.width
            elems.append(RLImage(logo_path, width=40*mm, height=40*mm*ratio))
        # Metadata including questions
        meta = f"Project {ctx['project_no']} | Client: {ctx['client_name']} | Industry: {ctx['industry']} | Generated: {datetime.now():%Y-%m-%d %H:%M}"
        elems.append(Paragraph(meta, normal)); elems.append(Spacer(1,5*mm))
        elems.append(Paragraph("Questions:", heading));
        for q in ctx['questions']:
            elems.append(Paragraph(f"- {q}", normal));
        elems.append(PageBreak())
        # Exec page
        elems.append(Paragraph("Executive Summary", heading))
        for line in exec_text.split("\n"): elems.append(Paragraph(f"- {line}", normal))
        elems.append(PageBreak())
        # Narrative page
        elems.append(Paragraph("Narrative Summary", heading))
        elems.append(Paragraph(narrative, normal)); elems.append(PageBreak())
        # Ideas page
        elems.append(Paragraph("Ideas Worth Exploring", heading))
        for line in ideas_text.split("\n"): elems.append(Paragraph(f"- {line}", normal))
        elems.append(PageBreak())
        # Quotes page
        elems.append(Paragraph("Top Quotes", heading))
        for rid, txt in quotes: elems.append(Paragraph(f"<b>{rid}</b>: {txt}", normal))
        doc.build(elems)
        buf.seek(0)
        st.download_button("⬇️ Download PDF", buf,
            file_name=f"OptiCoder_{ctx['project_no']}.pdf", mime='application/pdf')
    else:
        st.info("PDF unavailable — install reportlab.")

    # Action buttons
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🔄 Re-run with feedback"): st.experimental_rerun()
    with col2:
        if st.button("➡️ Next Question"): st.session_state.raw = ''; st.experimental_rerun()
    with col3:
        if st.button("➕ New Project"): st.session_state.clear(); st.experimental_rerun()
    with col4:
        if st.button("❌ Quit"): st.stop()

# Sidebar context
st.sidebar.header("Project Context")
for k, v in ctx.items(): st.sidebar.markdown(f"**{k.replace('_',' ').title()}:** {v}")







