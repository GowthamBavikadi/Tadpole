# brain_ai.py — Multi-provider AI cascade, intent detection, and text refinement.
#
# Provider priority (falls back automatically on failure / missing key):
#   1. Groq          — fastest free cloud (requires GROQ_API_KEY)
#   2. Google Gemini — generous free tier (requires GEMINI_API_KEY)
#   3. Pollinations  — zero-key public endpoint, always available
#   4. NVIDIA NIM    — fallback cloud (requires NVIDIA_API_KEY)
#
# Local NLP refiner (polish_raw_text_locally) runs offline with no API call:
#   - Strips conversational prefixes ("I found a crazy idea for...", "make a task of me having to...")
#   - Strips trailing filler ("...need to do it", "...have to try this")
#   - Normalises tech terms (github -> GitHub, readme -> README, api -> API)
#   - Produces a crisp Title + Executive Summary for any raw drop.

import os
import base64
import json
import re
from datetime import datetime, timedelta
import requests
from typing import Generator
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

_HTTP = requests.Session()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
if NVIDIA_API_KEY and not NVIDIA_API_KEY.startswith("Bearer "):
    NVIDIA_API_KEY = f"Bearer {NVIDIA_API_KEY}"

NVIDIA_INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

NVIDIA_CHAT_MODELS = [
    "meta/llama-3.3-70b-instruct",
    "meta/llama-3.1-70b-instruct",
    "mistralai/mistral-large-2-instruct",
    "meta/llama-3.1-8b-instruct",
]
NVIDIA_VISION_MODELS = [
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-3.2-90b-vision-instruct",
]

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

_gemini_client = None
LAST_ACTIVE_PROVIDER = "Apple Intelligence Cloud"


def get_active_provider_label() -> str:
    return LAST_ACTIVE_PROVIDER


def get_gemini_client():
    global _gemini_client
    if _gemini_client is None and GEMINI_API_KEY.startswith("AIza"):
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        except Exception:
            pass
    return _gemini_client


SYSTEM_PROMPT = """You are Gowtham's Second-Brain AI.
- Direct, concise, zero filler.
- Always rewrite messy raw input into clear, polished titles and descriptions."""


def _build_messages(messages: list, custom_system: str = None) -> list:
    out = [{"role": "system", "content": custom_system or SYSTEM_PROMPT}]
    for msg in messages:
        if msg["role"] == "system":
            continue
        out.append({"role": msg["role"], "content": msg["content"]})
    return out


def _call_cloud_cascade(messages: list, temperature: float = 0.2, max_tokens: int = 900) -> tuple[str | None, str | None]:
    global LAST_ACTIVE_PROVIDER

    # 1. Groq Free Cloud if configured
    if GROQ_API_KEY:
        try:
            resp = _HTTP.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={"model": "llama-3.3-70b-versatile", "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                timeout=7,
            )
            if resp.status_code == 200:
                LAST_ACTIVE_PROVIDER = "Groq Cloud"
                return resp.json()["choices"][0]["message"]["content"], "llama-3.3-70b-versatile"
        except Exception:
            pass

    # 2. Google Gemini Free Cloud if AIza key is configured
    client = get_gemini_client()
    if client:
        for gm in ["gemini-2.5-flash", "gemini-2.0-flash"]:
            try:
                full_prompt = "\n\n".join(f"{m['role'].upper()}:\n{m['content']}" for m in messages)
                res = client.models.generate_content(model=gm, contents=full_prompt)
                if res and res.text:
                    LAST_ACTIVE_PROVIDER = "Gemini Cloud"
                    return res.text.strip(), gm
            except Exception:
                continue

    # 3. Free Zero-Key Cloud OpenAI Endpoint (Pollinations AI — instant & 0 MB Mac RAM)
    try:
        resp = _HTTP.post(
            "https://text.pollinations.ai/openai",
            headers={"Content-Type": "application/json"},
            json={"model": "openai", "messages": messages, "temperature": temperature},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            reply = data.get("choices", [{}])[0].get("message", {}).get("content")
            if reply:
                LAST_ACTIVE_PROVIDER = "Cloud AI"
                return reply.strip(), "openai-fast"
    except Exception:
        pass

    # 4. NVIDIA NIM Cloud Cascade
    if NVIDIA_API_KEY:
        headers = {"Authorization": NVIDIA_API_KEY, "Accept": "application/json"}
        for m in NVIDIA_CHAT_MODELS:
            try:
                resp = _HTTP.post(
                    NVIDIA_INVOKE_URL,
                    headers=headers,
                    json={"model": m, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, "stream": False},
                    timeout=9,
                )
                if resp.status_code == 200:
                    reply = resp.json()["choices"][0]["message"]["content"]
                    short_name = m.split("/")[-1][:16]
                    LAST_ACTIVE_PROVIDER = f"Cloud • {short_name}"
                    return reply, m
            except Exception:
                continue

    return None, None


def chat(messages: list, model: str = None, custom_system: str = None) -> tuple[str, str]:
    built = _build_messages(messages, custom_system=custom_system)
    reply, used_model = _call_cloud_cascade(built, temperature=0.35)
    if reply is not None:
        return reply, used_model
    raise RuntimeError("Cloud AI unreachable.")


def stream_chat(messages: list, model: str = None) -> Generator[str, None, None]:
    reply, _ = chat(messages, model=model)
    yield reply


# ─── SMART INTENT DETECTION & EXECUTIVE SENTENCE REFINER ───
COMMON_TYPOS = {
    r"\btommorow\b": "tomorrow",
    r"\breadmefile\b": "README file",
    r"\btomorroww\b": "tomorrow",
    r"\btmrw\b": "tomorrow",
    r"\btmr\b": "tomorrow",
    r"\ba jeans\b": "a pair of jeans",
    r"\ba shoes\b": "a pair of shoes",
    r"\ba glasses\b": "a pair of glasses",
    r"\ba scissors\b": "a pair of scissors",
    r"\babt\b": "about",
    r"\bmsg\b": "message",
    r"\bu\b": "you",
    r"\bur\b": "your",
    r"\bpls\b": "please",
    r"\bplz\b": "please",
    r"\bgonna\b": "going to",
    r"\bwanna\b": "want to",
    r"\bgotta\b": "need to",
}

TECH_TERMS = {
    "github": "GitHub",
    "gitlab": "GitLab",
    "readme": "README",
    "api": "API",
    "apis": "APIs",
    "ui": "UI",
    "ux": "UX",
    "ai": "AI",
    "llm": "LLM",
    "macos": "macOS",
    "ios": "iOS",
    "ipad": "iPad",
    "iphone": "iPhone",
    "siri": "Siri",
    "sql": "SQL",
    "sqlite": "SQLite",
    "pdf": "PDF",
    "url": "URL",
    "css": "CSS",
    "html": "HTML",
    "js": "JavaScript",
    "ts": "TypeScript",
    "py": "Python",
    "aws": "AWS",
    "gcp": "GCP",
    "pr": "PR",
}


def is_question_text(text: str) -> bool:
    s = text.strip()
    if not s or os.path.exists(s.strip("'\"")) or s.startswith("file://") or re.match(r"^https?://\S+$", s):
        return False
    if is_task_text(s):
        return False
    if s.endswith("?") or s.startswith("?"):
        return True
    first_words = s.lower().split()
    if not first_words:
        return False
    q_starters = {
        "what", "what's", "whats", "why", "how", "when", "where", "who", "which",
        "whose", "whom", "can", "could", "would", "should", "is", "are", "was",
        "were", "do", "does", "did", "will", "explain", "tell", "define", "compare",
        "calculate", "solve", "meaning", "difference"
    }
    return first_words[0] in q_starters


def is_task_text(text: str) -> bool:
    """
    Detect if the user's input is a Task vs. an Idea.
    If the user explicitly mentions 'idea', 'concept', or 'thought' (and NOT 'task'/'todo'/'remind'),
    it is always treated as an Idea even if they say 'need to do it' at the end!
    """
    low = text.lower().strip()
    if not low:
        return False
    if re.search(r"\b(idea|concept|thought|brainstorm|inspiration)\b", low) and not re.search(r"\b(task|todo|to-do|remind|reminder)\b", low):
        return False

    task_patterns = [
        r"\btask\b",
        r"\btodo\b",
        r"\bto-do\b",
        r"\bremind\b",
        r"\breminder\b",
        r"\bhave to\b",
        r"\bhaving to\b",
        r"\bneed to\b",
        r"\bmust\b",
        r"\bgotta\b",
        r"\bdon'?t forget to\b",
        r"\bremember to\b",
        r"^(buy|pay|call|email|send|submit|finish|complete|schedule|book|fix|clean|study|prepare|review|pick up)\b",
        r"\b(by tomorrow|by tommorow|tomorrow|tommorow|tonight|by monday|by tuesday|by wednesday|by thursday|by friday|by saturday|by sunday)\b",
    ]
    return any(re.search(pat, low) for pat in task_patterns)


def extract_due_date(text: str) -> str | None:
    low = text.lower()
    for pat, repl in COMMON_TYPOS.items():
        low = re.sub(pat, repl, low)

    today = datetime.now()

    m_iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", low)
    if m_iso:
        return m_iso.group(1)

    if re.search(r"\b(tomorrow|tmrw)\b", low):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if re.search(r"\b(today|tonight)\b", low):
        return today.strftime("%Y-%m-%d")
    if re.search(r"\bday after tomorrow\b", low):
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
    if re.search(r"\bnext week\b", low):
        return (today + timedelta(days=7)).strftime("%Y-%m-%d")

    m_in_days = re.search(r"\bin\s+(\d+)\s+days?\b", low)
    if m_in_days:
        return (today + timedelta(days=int(m_in_days.group(1)))).strftime("%Y-%m-%d")

    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6
    }
    for day_name, target_wd in weekdays.items():
        if re.search(rf"\b(next\s+|on\s+|by\s+)?{day_name}\b", low):
            days_ahead = (target_wd - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    return None


def _smart_title_case(phrase: str) -> str:
    small_words = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "with", "by", "from"}
    words = phrase.split()
    out = []
    for i, w in enumerate(words):
        clean_w = w.strip(".,!?:;\"'()[]{}")
        low_w = clean_w.lower()
        if low_w in TECH_TERMS:
            out.append(TECH_TERMS[low_w])
        elif i == 0 or i == len(words) - 1 or low_w not in small_words:
            out.append(clean_w.capitalize())
        else:
            out.append(low_w)
    return " ".join(out)


def polish_raw_text_locally(raw_text: str, is_task: bool = False) -> tuple[str, str]:
    """
    Transforms conversational raw input into a crisp, executive Title and a refined Summary sentence.
    Examples:
      - 'I found a crazy idea for my github readme file need to do it'
        -> Title:   'GitHub README Concept'
        -> Summary: 'Design and implement the new concept for the GitHub README file.'
      - 'make a task of me having to buy a jeans tommorow'
        -> Title:   'Buy a Pair of Jeans'
        -> Summary: 'Purchase a pair of jeans tomorrow.'
    """
    s = raw_text.strip()
    for pat, repl in COMMON_TYPOS.items():
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)

    core = s
    # 1. Strip leading conversational filler phrases
    leading_wrappers = [
        r"^(hey\s+|hi\s+|okay\s+|so\s+|well\s+)+",
        r"^(please\s+)?(can you\s+|could you\s+)?(make|create|add|set|put|write|save|note|record)\s+(a\s+|an\s+|new\s+|this\s+)?(task|todo|to-do|reminder|idea|note|box|thought)\s*(for me\s*|of me\s*|about\s*|that\s*|to\s*|for\s*|on\s*|:|-)*",
        r"^(i\s+just\s+|i\s+recently\s+|i\s+)?(found|had|got|came\s+up\s+with|thought\s+of|saw|discovered|have)\s+(a\s+|an\s+|this\s+|some\s+)?(really\s+|super\s+|very\s+)?(crazy\s+|cool\s+|great\s+|good\s+|awesome\s+|amazing\s+|insane\s+|nice\s+|new\s+|interesting\s+|wild\s+|sick\s+)?(idea|concept|thought|plan|design|way|feature|project)\s*(for\s+|about\s+|on\s+|to\s+|of\s+|regarding\s*|:|-)*",
        r"^(of\s+me\s+|for\s+me\s+)?(having\s+to|needing\s+to|that\s+i\s+have\s+to|that\s+i\s+need\s+to|that\s+i\s+want\s+to|that\s+i\s+should|to)\s+",
        r"^(i\s+have\s+to|i\s+need\s+to|i\s+want\s+to|i\s+must|i\s+should|i\s+gotta|remind\s+me\s+to|remember\s+to|don'?t\s+forget\s+to|i\s+ was\s+thinking\s+of|i\s+was\s+thinking\s+about)\s+",
        r"^(my\s+idea\s+is\s+to|my\s+idea\s+is\s+that|idea\s+for|idea\s+about|idea\s*:|task\s*:|todo\s*:)\s*",
    ]
    for _ in range(4):
        for pat in leading_wrappers:
            core = re.sub(pat, "", core, flags=re.IGNORECASE).strip()

    # 2. Strip trailing filler clauses ("need to do it", "have to try this", "should build it", etc.)
    trailing_wrappers = [
        r"[,.;:\-\s]+(and\s+|so\s+)?(i\s+)?(really\s+)?(need|have|want|gotta|should|must|going|plan)\s+to\s+(do|try|build|make|implement|test|check|work\s+on|use|finish|complete)\s+(it|this|that|them|soon|later|now|sometime).*$",
        r"[,.;:\-\s]+(need|have|gotta)\s+to\s+(do|try|build|make|implement)\s*(it|this|that)?.*$",
        r"[,.;:\-\s]+(let'?s\s+do\s+it|will\s+do\s+it\s+later|do\s+it\s+soon).*$",
    ]
    for pat in trailing_wrappers:
        core = re.sub(pat, "", core, flags=re.IGNORECASE).strip()

    # 3. Strip leading possessive pronouns ("my ", "our ") for cleaner titles
    core = re.sub(r"^(making|building|creating|designing|doing|having)\s+(a\s+|an\s+|the\s+)?(really\s+|super\s+|very\s+)?(crazy\s+|cool\s+|great\s+|good\s+|awesome\s+|amazing\s+|new\s+|custom\s+)?", "", core, flags=re.IGNORECASE).strip()
    core = re.sub(r"\bfor\s+my\s+([A-Za-z0-9_]+)$", r"for \1", core, flags=re.IGNORECASE).strip()
    subject = re.sub(r"^(my|our|a|an)\s+", "", core, flags=re.IGNORECASE).strip(" .,!-")

    # 4. Separate any trailing time expression for tasks
    time_match = re.search(
        r"\s+\b(by\s+tomorrow|tomorrow|tonight|today|next\s+week|on\s+\w+day|by\s+\w+day|in\s+\d+\s+days?)\b.*$",
        subject,
        flags=re.IGNORECASE
    )
    time_suffix = time_match.group(0).strip() if time_match else ""
    title_subject = subject[:time_match.start()].strip(" .,!-") if time_match else subject

    if not title_subject:
        title_subject = core.strip(" .,!-") or ("Action Item" if is_task else "New Concept")

    # Normalize tech terms in subject
    subj_words = title_subject.split()
    norm_words = [TECH_TERMS.get(w.lower(), w) for w in subj_words]
    norm_subject = " ".join(norm_words)

    if is_task:
        clean_title = _smart_title_case(" ".join(norm_words[:7]))
        # Build polished action description
        desc_body = norm_subject
        if desc_body.lower().startswith("buy "):
            desc_body = "Purchase " + desc_body[4:]
        elif not re.match(r"^(purchase|buy|pay|call|email|send|submit|finish|complete|schedule|book|fix|clean|study|prepare|review|pick|build|create|update|write)\b", desc_body.lower()):
            desc_body = "Complete task: " + desc_body
        else:
            desc_body = desc_body[0].upper() + desc_body[1:]
        if time_suffix:
            desc_body = f"{desc_body.rstrip('.')} {time_suffix}."
        elif not desc_body.endswith("."):
            desc_body += "."
        return clean_title, desc_body
    else:
        # It's an Idea! Make the title a crisp concept header and the description a polished actionable summary
        short_words = norm_words[:6]
        clean_title = _smart_title_case(" ".join(short_words))
        if len(short_words) <= 4 and "concept" not in clean_title.lower() and "idea" not in clean_title.lower():
            clean_title = f"{clean_title} — Concept"

        # If the subject is a noun phrase (e.g., "GitHub README file"), turn it into a refined summary sentence
        first_w = norm_words[0].lower() if norm_words else ""
        if first_w in {"build", "create", "design", "develop", "make", "write", "add", "implement", "launch", "use"}:
            desc_sentence = norm_subject[0].upper() + norm_subject[1:]
            if not desc_sentence.endswith("."):
                desc_sentence += "."
        else:
            desc_sentence = f"Explore, design, and implement the new concept for {norm_subject}."
        return clean_title, desc_sentence


def describe_image(image_path: str, prompt: str = "Describe this image clearly. Extract any key text, tasks, or ideas.") -> str:
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    ext = os.path.splitext(image_path)[1].lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "webp": "webp"}.get(ext, "jpeg")
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64_image}"}},
            ],
        }
    ]
    if NVIDIA_API_KEY:
        headers = {"Authorization": NVIDIA_API_KEY, "Accept": "application/json"}
        for vm in NVIDIA_VISION_MODELS:
            try:
                resp = _HTTP.post(
                    NVIDIA_INVOKE_URL,
                    headers=headers,
                    json={"model": vm, "messages": messages, "temperature": 0.2, "max_tokens": 1200},
                    timeout=18,
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
            except Exception:
                continue
    return "[Could not analyze image with cloud AI.]"


def transcribe_audio(audio_path: str) -> str:
    client = get_gemini_client()
    if client:
        try:
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            res = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    "Transcribe the spoken audio completely and accurately.",
                    {"mime_type": "audio/mp4", "data": audio_bytes},
                ],
            )
            return res.text.strip()
        except Exception:
            pass
    return "[Audio transcription unavailable.]"


def check_focus_drift(user_message: str, focus_topic: str) -> bool:
    prompt = (
        f"Current focus: '{focus_topic}'.\n"
        f"Message: '{user_message[:300]}'\n"
        f"Is this message unrelated to the focus topic? Reply strictly 'yes' or 'no'."
    )
    try:
        reply, _ = chat([{"role": "user", "content": prompt}])
        return reply.strip().lower().startswith("yes")
    except Exception:
        return False


def summarise(text: str, context: str = "") -> str:
    prompt = f"{context}\n\nText to summarise:\n{text[:8000]}" if context else f"Summarise this:\n{text[:8000]}"
    reply, _ = chat([{"role": "user", "content": prompt}])
    return reply


def _extract_json_block(raw_str: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_str.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        cleaned = m.group(0)
    return json.loads(cleaned)


def _looks_unrefined(candidate: str, raw_input: str) -> bool:
    """Returns True if the AI returned something too close to the raw conversational sentence."""
    if not candidate or not candidate.strip():
        return True
    c_low = re.sub(r"[^a-z0-9\s]", "", candidate.lower()).strip()
    r_low = re.sub(r"[^a-z0-9\s]", "", raw_input.lower()).strip()
    if c_low == r_low or c_low in r_low and len(c_low) > len(r_low) * 0.75:
        return True
    bad_prefixes = ("i found a", "i had a", "make a task", "create a task", "remind me to", "i need to", "i have to")
    if c_low.startswith(bad_prefixes):
        return True
    return False


def triage_drop(raw_content: str, source: str = "", drop_hint: str = "") -> dict:
    today_str = datetime.now().strftime("%Y-%m-%d (%A)")
    extracted_urls = re.findall(r"https?://[^\s<>\"']+", raw_content)
    detected_task = is_task_text(raw_content)
    local_due = extract_due_date(raw_content)
    local_title, local_summary = polish_raw_text_locally(raw_content, is_task=detected_task)

    system_prompt = (
        f"You are an Apple Intelligence Executive Editor. Today is {today_str}.\n"
        "Rewrite the user's raw conversational message into a crisp, professional Title and a well-written Summary.\n"
        "NEVER echo conversational filler like 'I found a crazy idea for...', 'need to do it', or 'make a task of me having to...'.\n"
        "Return ONLY valid JSON with this schema:\n"
        "{\n"
        '  "title": "Crisp 2-5 word subject title (e.g., \'GitHub README Redesign\' or \'Buy a Pair of Jeans\')",\n'
        '  "summary": "1-2 sentence polished, professional description (e.g., \'Design and implement the new concept for the GitHub profile README.\')",\n'
        '  "type": "task" | "idea" | "document" | "link",\n'
        '  "due_date": "YYYY-MM-DD" or null,\n'
        '  "tags": ["#idea"] or ["#task"],\n'
        '  "links": ["https://..."]\n'
        "}"
    )

    prompt = f"Raw Input:\n{raw_content[:4000]}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    raw_json_str, _ = _call_cloud_cascade(messages, temperature=0.15, max_tokens=600)
    try:
        data = _extract_json_block(raw_json_str or "")
        ai_title = (data.get("title") or "").strip()
        if _looks_unrefined(ai_title, raw_content):
            ai_title = local_title

        ai_summary = (data.get("summary") or "").strip()
        if _looks_unrefined(ai_summary, raw_content):
            ai_summary = local_summary

        final_type = "task" if detected_task else ("idea" if "idea" in raw_content.lower() else data.get("type", "idea"))
        final_due = data.get("due_date") or local_due
        ai_links = data.get("links") if isinstance(data.get("links"), list) else []
        merged_links = list(dict.fromkeys(extracted_urls + [str(u) for u in ai_links if u]))

        return {
            "title": ai_title,
            "summary": ai_summary,
            "type": final_type,
            "due_date": final_due,
            "tags": data.get("tags") or (["#task"] if final_type == "task" else ["#idea"]),
            "links": merged_links,
        }
    except Exception:
        return {
            "title": local_title,
            "summary": local_summary,
            "type": "task" if detected_task else "idea",
            "due_date": local_due,
            "tags": ["#task"] if detected_task else ["#idea"],
            "links": extracted_urls,
        }


def query_notebook_brain(user_query: str, retrieved_chunks: list[dict], tasks: list[dict], focus: str) -> dict:
    today_str = datetime.now().strftime("%Y-%m-%d (%A)")
    sources_block = "\n\n".join(
        f"[Source #{i+1}: {c.get('title', 'Note')}]\n{c.get('chunk_text', '')}"
        for i, c in enumerate(retrieved_chunks)
    )

    system_prompt = (
        f"You are Gowtham's Apple Intelligence Second-Brain assistant. Today is {today_str}.\n"
        f"Active Focus: {focus}\n\n"
        f"Saved Ideas & Notes in Vault (use if relevant):\n{sources_block or 'None yet.'}\n\n"
        "Answer the user's question directly, clearly, and concisely.\n"
        "Respond with valid JSON ONLY:\n"
        "{\n"
        '  "reply": "Direct, helpful answer to the user\'s question",\n'
        '  "cited_titles": []\n'
        "}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]
    raw_str, _ = _call_cloud_cascade(messages, temperature=0.3, max_tokens=1000)
    if not raw_str:
        return {"status": "error", "reply": "Cloud AI unreachable. Check internet connection.", "added_tasks": 0, "citations": []}

    try:
        parsed = _extract_json_block(raw_str)
        return {
            "status": "success",
            "reply": parsed.get("reply", raw_str),
            "citations": parsed.get("cited_titles", []),
            "new_tasks": [],
        }
    except Exception:
        return {
            "status": "success",
            "reply": raw_str.strip(),
            "citations": [],
            "new_tasks": [],
        }
