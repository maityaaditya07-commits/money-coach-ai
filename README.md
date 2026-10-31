# Personal Finance Coach 💰

An intelligent, dual-stack **Personal Finance Coach** application built with a FastAPI backend (running on Render) and a Streamlit frontend (hosted on Streamlit Community Cloud). It features AI-powered financial coaching, automated statement parsing, budgeting metrics, and smart spending nudges.

---

## 🚀 Live Links
* **Frontend (Streamlit):** [https://money-coach-dqnbaudn2hqks6fan2obyf.streamlit.app](https://money-coach-dqnbaudn2hqks6fan2obyf.streamlit.app)
* **Backend API (FastAPI):** [https://money-coach-r0xc.onrender.com](https://money-coach-r0xc.onrender.com)
* **API Documentation (Swagger):** [https://money-coach-r0xc.onrender.com/docs](https://money-coach-r0xc.onrender.com/docs)

---

## 🛠️ Tech Stack
* **Frontend:** Streamlit, Python, Requests
* **Backend:** FastAPI, Uvicorn, Pydantic, SQLite
* **AI Integration:** Google Gemini API (`google-genai`)
* **Deployment:** Streamlit Community Cloud (Frontend) & Render (Backend)

---

## 📂 Project Structure
```text
money-coach/
├── main.py              # Streamlit frontend application
├── backend/             # FastAPI backend services
│   ├── main.py          # FastAPI app entry point
│   ├── database.py      # SQLite configuration and models
│   └── services/        # AI parsing & nudge generation logic
├── requirements.txt     # Python dependencies
└── README.md            # Project documentation
