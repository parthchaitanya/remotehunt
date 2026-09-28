"""Skill taxonomy shared by the resume parser, matcher, skill-gap analysis and guardrails.

Each canonical skill has a display name, a category and aliases. Aliases are matched
case-insensitively on word boundaries unless listed in CASE_SENSITIVE / CUSTOM_PATTERNS.
"""
from __future__ import annotations

import re
from functools import lru_cache

# canonical key -> (display name, category, aliases)
SKILLS: dict[str, tuple[str, str, list[str]]] = {
    # Languages
    "python": ("Python", "language", ["python", "python3"]),
    "java": ("Java", "language", ["java"]),
    "javascript": ("JavaScript", "language", ["javascript", "js", "ecmascript"]),
    "typescript": ("TypeScript", "language", ["typescript"]),
    "golang": ("Go", "language", ["golang"]),
    "rust": ("Rust", "language", ["rust"]),
    "cpp": ("C++", "language", ["c++", "cpp"]),
    "csharp": ("C#", "language", ["c#", "csharp", ".net", "dotnet"]),
    "ruby": ("Ruby", "language", ["ruby"]),
    "php": ("PHP", "language", ["php"]),
    "scala": ("Scala", "language", ["scala"]),
    "kotlin": ("Kotlin", "language", ["kotlin"]),
    "r_lang": ("R", "language", []),
    "sql": ("SQL", "data", ["sql"]),
    "bash": ("Bash", "tools", ["bash", "shell scripting", "shell script"]),
    # Web / backend
    "django": ("Django", "backend", ["django"]),
    "flask": ("Flask", "backend", ["flask"]),
    "fastapi": ("FastAPI", "backend", ["fastapi"]),
    "rest_api": ("REST APIs", "backend", ["rest api", "rest apis", "restful", "rest", "restful apis"]),
    "graphql": ("GraphQL", "backend", ["graphql"]),
    "grpc": ("gRPC", "backend", ["grpc"]),
    "nodejs": ("Node.js", "backend", ["node.js", "nodejs", "node js"]),
    "express": ("Express", "backend", ["express.js", "expressjs"]),
    "react": ("React", "frontend", ["react", "react.js", "reactjs"]),
    "nextjs": ("Next.js", "frontend", ["next.js", "nextjs"]),
    "vue": ("Vue", "frontend", ["vue", "vue.js", "vuejs"]),
    "angular": ("Angular", "frontend", ["angular"]),
    "html": ("HTML", "frontend", ["html", "html5"]),
    "css": ("CSS", "frontend", ["css", "css3"]),
    "tailwind": ("Tailwind CSS", "frontend", ["tailwind", "tailwindcss"]),
    "streamlit": ("Streamlit", "frontend", ["streamlit"]),
    "celery": ("Celery", "backend", ["celery"]),
    "microservices": ("Microservices", "backend", ["microservices", "microservice"]),
    "sqlalchemy": ("SQLAlchemy", "backend", ["sqlalchemy"]),
    "pydantic": ("Pydantic", "backend", ["pydantic"]),
    "asyncio": ("asyncio", "backend", ["asyncio", "async python"]),
    # Data stores
    "mysql": ("MySQL", "database", ["mysql"]),
    "postgresql": ("PostgreSQL", "database", ["postgresql", "postgres", "psql"]),
    "sqlite": ("SQLite", "database", ["sqlite"]),
    "mongodb": ("MongoDB", "database", ["mongodb", "mongo"]),
    "redis": ("Redis", "database", ["redis"]),
    "elasticsearch": ("Elasticsearch", "database", ["elasticsearch", "opensearch"]),
    "nosql": ("NoSQL", "database", ["nosql"]),
    "snowflake": ("Snowflake", "data", ["snowflake"]),
    "bigquery": ("BigQuery", "data", ["bigquery", "big query"]),
    "redshift": ("Redshift", "data", ["redshift"]),
    "databricks": ("Databricks", "data", ["databricks"]),
    "vector_db": ("Vector databases", "ai", ["vector database", "vector databases", "vector db", "pinecone",
                                             "weaviate", "qdrant", "chromadb", "chroma", "faiss", "milvus", "pgvector"]),
    # Data analysis / BI
    "pandas": ("Pandas", "data", ["pandas"]),
    "numpy": ("NumPy", "data", ["numpy"]),
    "scipy": ("SciPy", "data", ["scipy"]),
    "matplotlib": ("Matplotlib", "data", ["matplotlib"]),
    "seaborn": ("Seaborn", "data", ["seaborn"]),
    "plotly": ("Plotly", "data", ["plotly"]),
    "excel": ("Excel", "data", ["excel", "ms excel", "microsoft excel", "advanced excel", "spreadsheets", "google sheets"]),
    "power_bi": ("Power BI", "data", ["power bi", "powerbi"]),
    "tableau": ("Tableau", "data", ["tableau"]),
    "looker": ("Looker", "data", ["looker", "looker studio"]),
    "statistics": ("Statistics", "data", ["statistics", "statistical analysis", "statistical", "hypothesis testing",
                                          "a/b testing", "ab testing"]),
    "data_analysis": ("Data analysis", "data", ["data analysis", "data analytics", "exploratory data analysis", "eda"]),
    "data_visualization": ("Data visualization", "data", ["data visualization", "data visualisation", "dashboards",
                                                          "dashboard"]),
    "data_cleaning": ("Data cleaning", "data", ["data cleaning", "data wrangling", "data preprocessing", "preprocessing"]),
    "etl": ("ETL", "data", ["etl", "elt", "data pipelines", "data pipeline"]),
    "airflow": ("Airflow", "data", ["airflow", "apache airflow"]),
    "spark": ("Spark", "data", ["spark", "pyspark", "apache spark"]),
    "kafka": ("Kafka", "data", ["kafka"]),
    "dbt": ("dbt", "data", ["dbt"]),
    "jupyter": ("Jupyter", "tools", ["jupyter", "jupyter notebook", "jupyter notebooks", "jupyterlab"]),
    "google_colab": ("Google Colab", "tools", ["google colab", "colab"]),
    # ML / AI
    "machine_learning": ("Machine learning", "ml", ["machine learning", "ml"]),
    "deep_learning": ("Deep learning", "ml", ["deep learning", "neural networks", "neural network"]),
    "supervised_learning": ("Supervised learning", "ml", ["supervised learning"]),
    "unsupervised_learning": ("Unsupervised learning", "ml", ["unsupervised learning", "clustering"]),
    "regression": ("Regression", "ml", ["regression", "linear regression", "logistic regression"]),
    "classification": ("Classification", "ml", ["classification", "classifier"]),
    "scikit_learn": ("scikit-learn", "ml", ["scikit-learn", "scikit learn", "sklearn"]),
    "tensorflow": ("TensorFlow", "ml", ["tensorflow", "tf.keras"]),
    "keras": ("Keras", "ml", ["keras"]),
    "pytorch": ("PyTorch", "ml", ["pytorch", "torch"]),
    "xgboost": ("XGBoost", "ml", ["xgboost", "lightgbm", "catboost"]),
    "nlp": ("NLP", "ai", ["nlp", "natural language processing"]),
    "text_processing": ("Text processing", "ai", ["text processing", "text preprocessing"]),
    "tokenization": ("Tokenization", "ai", ["tokenization", "tokenisation"]),
    "sentiment_analysis": ("Sentiment analysis", "ai", ["sentiment analysis"]),
    "computer_vision": ("Computer vision", "ai", ["computer vision", "opencv", "image processing"]),
    "llm": ("LLMs", "ai", ["llm", "llms", "large language model", "large language models", "gpt", "genai",
                          "generative ai", "gen ai"]),
    "rag": ("RAG", "ai", ["rag", "retrieval augmented generation", "retrieval-augmented generation"]),
    "prompt_engineering": ("Prompt engineering", "ai", ["prompt engineering", "prompting"]),
    "langchain": ("LangChain", "ai", ["langchain", "langgraph"]),
    "llamaindex": ("LlamaIndex", "ai", ["llamaindex", "llama index", "llama-index"]),
    "huggingface": ("Hugging Face", "ai", ["hugging face", "huggingface", "transformers library"]),
    "openai_api": ("OpenAI API", "ai", ["openai api", "openai sdk", "openai models"]),
    "embeddings": ("Embeddings", "ai", ["embeddings", "sentence transformers", "sentence-transformers"]),
    "fine_tuning": ("Fine-tuning", "ai", ["fine-tuning", "fine tuning", "finetuning", "lora", "peft"]),
    "ai_agents": ("AI agents", "ai", ["ai agents", "agentic", "llm agents", "multi-agent"]),
    "mlops": ("MLOps", "ml", ["mlops", "mlflow", "kubeflow", "model deployment", "model serving"]),
    "feature_engineering": ("Feature engineering", "ml", ["feature engineering", "feature scaling", "feature selection"]),
    "model_evaluation": ("Model evaluation", "ml", ["model evaluation", "rmse", "cross-validation", "cross validation"]),
    "time_series": ("Time series", "ml", ["time series", "forecasting"]),
    # Cloud / DevOps
    "aws": ("AWS", "cloud", ["aws", "amazon web services", "ec2", "s3", "aws lambda", "sagemaker", "elastic beanstalk"]),
    "gcp": ("GCP", "cloud", ["gcp", "google cloud", "google cloud platform", "vertex ai"]),
    "azure": ("Azure", "cloud", ["azure", "microsoft azure"]),
    "docker": ("Docker", "devops", ["docker", "dockerfile", "containers", "containerization"]),
    "kubernetes": ("Kubernetes", "devops", ["kubernetes", "k8s"]),
    "terraform": ("Terraform", "devops", ["terraform"]),
    "ci_cd": ("CI/CD", "devops", ["ci/cd", "ci cd", "github actions", "gitlab ci", "jenkins", "continuous integration"]),
    "linux": ("Linux", "devops", ["linux", "unix"]),
    "git": ("Git", "tools", ["git", "github", "version control"]),
    "vscode": ("VS Code", "tools", ["vs code", "vscode", "visual studio code"]),
    "sharepoint": ("SharePoint", "tools", ["sharepoint"]),
    "jira": ("Jira", "tools", ["jira"]),
    # Quality
    "testing": ("Testing", "quality", ["unit testing", "unit tests", "test automation", "automated testing",
                                      "web testing", "end-to-end testing", "qa testing", "tdd"]),
    "pytest": ("pytest", "quality", ["pytest", "unittest"]),
    "selenium": ("Selenium", "quality", ["selenium", "playwright", "cypress"]),
    # Misc
    "web_scraping": ("Web scraping", "data", ["web scraping", "beautifulsoup", "scrapy"]),
    "oop": ("OOP", "cs", ["oop", "object-oriented programming", "object oriented programming"]),
    "dsa": ("Data structures & algorithms", "cs", ["data structures", "data structures and algorithms", "dsa"]),
    "system_design": ("System design", "cs", ["system design", "distributed systems"]),
    "agile": ("Agile", "process", ["agile", "scrum", "kanban"]),
    "portal_development": ("Portal development", "backend", ["portal development", "web portal"]),
    "communication": ("Communication", "soft", ["communication", "communicator", "stakeholder management"]),
}

# Aliases that must match with exact case (too ambiguous otherwise).
CASE_SENSITIVE: dict[str, list[str]] = {
    "r_lang": [r"(?:^|[\s,(/])R(?=\s*(?:[,/)]|$|programming|language|studio))", r"\bRStudio\b"],
    "golang": [r"(?:[,(/]\s?)Go\b", r"\bGo(?=\s?[,/)])", r"\bGo(?= programming| language)"],
    "rest_api": [r"\bREST\b"],
}

# Skills that imply others (for "do I have it?" checks, never for claims about depth).
IMPLIES: dict[str, list[str]] = {
    "mysql": ["sql"], "postgresql": ["sql"], "sqlite": ["sql"], "mongodb": ["nosql"], "redis": ["nosql"],
    "pandas": ["python", "data_analysis"], "numpy": ["python"], "scikit_learn": ["python", "machine_learning"],
    "matplotlib": ["python", "data_visualization"], "seaborn": ["python", "data_visualization"],
    "plotly": ["data_visualization"], "flask": ["python"], "django": ["python"], "fastapi": ["python"],
    "streamlit": ["python", "data_visualization"], "supervised_learning": ["machine_learning"],
    "unsupervised_learning": ["machine_learning"], "regression": ["machine_learning"],
    "classification": ["machine_learning"], "pytorch": ["deep_learning", "python"],
    "tensorflow": ["deep_learning", "python"], "keras": ["deep_learning"], "sentiment_analysis": ["nlp"],
    "tokenization": ["nlp"], "text_processing": ["nlp"], "langchain": ["llm"], "rag": ["llm"],
    "power_bi": ["data_visualization"], "tableau": ["data_visualization"], "jupyter": ["python"],
    "pytest": ["testing"], "selenium": ["testing"], "spark": ["etl"], "airflow": ["etl"],
}

DISPLAY = {k: v[0] for k, v in SKILLS.items()}
CATEGORY = {k: v[1] for k, v in SKILLS.items()}

@lru_cache
def _compiled() -> list[tuple[str, re.Pattern[str], tuple[str, ...]]]:
    """(key, pattern, needles). A pattern only runs if one of its lowercase needles occurs in the text."""
    out: list[tuple[str, re.Pattern[str], tuple[str, ...]]] = []
    for key, (_, _, aliases) in SKILLS.items():
        parts, needles = [], set()
        for alias in aliases:
            if alias in ("rest",):  # handled case-sensitively
                continue
            esc = re.escape(alias).replace(r"\ ", r"[\s-]+")
            parts.append(rf"(?<![\w+#.]){esc}(?![\w+#])")
            needles.add(alias.lower().split()[0].split("-")[0])
        if parts:
            out.append((key, re.compile("|".join(parts), re.IGNORECASE), tuple(needles)))
        for pat in CASE_SENSITIVE.get(key, []):
            out.append((key, re.compile(pat), ()))
    return out


def _candidates(text: str):
    low = text.lower()
    for key, pat, needles in _compiled():
        if needles and not any(n in low for n in needles):
            continue
        yield key, pat


def extract_skills(text: str) -> list[str]:
    """Return canonical skill keys found in text, in order of first appearance."""
    if not text:
        return []
    found: dict[str, int] = {}
    for key, pat in _candidates(text):
        m = pat.search(text)
        if m and (key not in found or m.start() < found[key]):
            found[key] = m.start()
    return [k for k, _ in sorted(found.items(), key=lambda kv: kv[1])]


def skill_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not text:
        return counts
    for key, pat in _candidates(text):
        n = len(pat.findall(text))
        if n:
            counts[key] = counts.get(key, 0) + n
    return counts


def expand_implied(skills: set[str] | list[str]) -> set[str]:
    out = set(skills)
    frontier = list(out)
    while frontier:
        s = frontier.pop()
        for imp in IMPLIES.get(s, []):
            if imp not in out:
                out.add(imp)
                frontier.append(imp)
    return out


def normalize_skill_name(name: str) -> str | None:
    """Map a free-text skill name (e.g. from a resume skills line) to a canonical key."""
    found = extract_skills(name)
    return found[0] if found else None


def display(keys: list[str] | set[str]) -> list[str]:
    return [DISPLAY.get(k, k) for k in keys]


# Role skill maps used for skill-gap analysis and ATS keyword alignment.
ROLE_SKILLS: dict[str, dict[str, list[str]]] = {
    "Python Developer": {
        "core": ["python", "sql", "rest_api", "git", "django", "flask", "fastapi", "testing", "oop"],
        "nice": ["docker", "postgresql", "aws", "linux", "ci_cd", "pytest", "redis", "celery", "sqlalchemy",
                 "asyncio", "dsa"],
    },
    "Data Analyst": {
        "core": ["sql", "excel", "python", "pandas", "data_visualization", "statistics", "data_analysis",
                 "data_cleaning"],
        "nice": ["power_bi", "tableau", "looker", "numpy", "matplotlib", "seaborn", "bigquery", "etl",
                 "communication"],
    },
    "AI Engineer": {
        "core": ["python", "machine_learning", "llm", "nlp", "deep_learning", "pytorch", "rag", "embeddings",
                 "prompt_engineering"],
        "nice": ["tensorflow", "huggingface", "langchain", "vector_db", "fastapi", "docker", "mlops", "aws",
                 "fine_tuning", "ai_agents", "scikit_learn"],
    },
}


def role_family(title: str, role_keywords: dict[str, list[str]] | None = None) -> str:
    """Best-effort mapping of a job title onto one of the target role families."""
    t = (title or "").lower()
    defaults = {
        "AI Engineer": ["ai engineer", "machine learning", "ml engineer", "llm", "genai", "nlp", "data scientist",
                        "deep learning", "ai/ml", "applied scientist", " ai ", "artificial intelligence"],
        "Data Analyst": ["data analyst", "analytics", "business analyst", "bi analyst", "reporting analyst",
                         "business intelligence", "insights analyst", "data engineer"],
        "Python Developer": ["python", "backend", "back-end", "django", "flask", "fastapi", "software engineer",
                             "software developer", "developer", "sde"],
    }
    kw = role_keywords or {}
    padded = f" {t} "
    for role in ("AI Engineer", "Data Analyst", "Python Developer"):
        words = set(defaults[role]) | {w.lower() for w in kw.get(role, [])}
        for w in words:
            if len(w) <= 3 and w.strip() not in {"ai", "ml", "sde", "nlp", "llm"}:
                continue
            if re.search(rf"(?<![a-z]){re.escape(w.strip())}(?![a-z])", padded):
                return role
    return ""
