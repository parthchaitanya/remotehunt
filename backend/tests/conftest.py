import os
import sys
import tempfile
from pathlib import Path

# Isolated data dir / DB for tests; must be set before app modules are imported.
_tmp = tempfile.mkdtemp(prefix="remotehunt-test-")
os.environ["DATA_DIR"] = _tmp
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["GROQ_API_KEY"] = ""  # tests never call the LLM
os.environ["FERNET_KEY"] = "q2mX7yJ0bP9x8oQ1Yx0mKZ2Y3m4n5b6v7c8x9z0a1s4="

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import init_db  # noqa: E402

init_db()

SAMPLE_RESUME_TEXT = """Asha Verma
+91 98765 43210 | asha.verma@example.com | github.com/ashav | linkedin.com/in/ashav
Professional Summary
Computer science student building data and ML applications with Python and SQL.
Education
Example Institute of Technology, Pune 2023-Present
Bachelor of Technology in Computer Science
Technical Skills
Programming: Python, Java
Libraries: Pandas, NumPy, Scikit-learn, Matplotlib
Web Technologies: Flask, Streamlit, HTML
Databases: MySQL, MongoDB
Tools & Platforms: Git, Jupyter Notebook
Projects
Sales Forecaster: Demand Prediction Model Github
Python, Pandas, Scikit-learn, Streamlit
• Built a regression model predicting weekly sales for 1,200 stores, cutting forecast error by
18% versus the baseline.
• Deployed an interactive Streamlit dashboard used by 40+ classmates.
Internship
Data Intern – Acme Analytics (Jun 2024 – Aug 2024)
Python, SQL, Excel
• Automated a weekly SQL reporting pipeline, saving 6 hours of manual work per week.
• Cleaned and analysed 50,000 customer records with Pandas to identify churn drivers.
Extracurricular Activities
Coding Club Lead (2024 – Present): Organised 3 hackathons with 300+ participants.
"""


@pytest.fixture
def sample_text():
    return SAMPLE_RESUME_TEXT


@pytest.fixture
def sample_parsed(sample_text):
    from app.resume.parser import parse_text

    return parse_text(sample_text)


@pytest.fixture
def profile():
    return {
        "candidate": {"target_roles": ["Python Developer", "Data Analyst", "AI Engineer"], "max_years_required": 2,
                      "utc_offset": 5.5, "timezone_tolerance_hours": 3.5,
                      "onsite_ok_locations": ["Noida", "Delhi", "Gurugram"]},
        "search": {"role_keywords": {}},
        "matching": {},
        "gmail": {},
    }
