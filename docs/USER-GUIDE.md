# SmartLearner — User Guide

**دليل المستخدم | User Guide**

Version: SmartLearner 2.0 (Graduation Project)  
Audience: Students using the web application  
Last updated: May 2026

---

## Table of Contents

1. [What is SmartLearner?](#1-what-is-smartlearner)
2. [Before You Start](#2-before-you-start)
3. [Create an Account and Sign In](#3-create-an-account-and-sign-in)
4. [Dashboard Overview](#4-dashboard-overview)
5. [Recommended Learning Path](#5-recommended-learning-path)
6. [Placement Test](#6-placement-test)
7. [Personalized Syllabus](#7-personalized-syllabus)
8. [Lessons and Quick Assessment](#8-lessons-and-quick-assessment)
9. [Q&A Tutor](#9-qa-tutor)
10. [Exams](#10-exams)
11. [Analytics](#11-analytics)
12. [Settings and Sign Out](#12-settings-and-sign-out)
13. [Icons and Progress States](#13-icons-and-progress-states)
14. [Troubleshooting](#14-troubleshooting)
15. [Quick Reference — URLs](#15-quick-reference--urls)

---

## 1. What is SmartLearner?

SmartLearner is an **adaptive** online learning platform. It does **not** give every student the same fixed course. Instead, it:

- Estimates your level with a **placement test**
- Builds a **personalized syllabus** from your results (including topics you need more practice on)
- Generates **lesson content** when you open a topic
- Offers a **quick quiz** after each lesson; if you struggle, the topic may split into **smaller sub-lessons**
- Provides an **AI tutor (Q&A)** grounded in your course material
- Shows **analytics** on your progress and weak areas

### Learning tracks

When you start placement, you choose a track:

| Track | Source material |
|-------|----------------|
| **Python Foundations** | Python for Everybody (PY4E) |
| **Deep Learning** | Deep Learning textbook scope |

> **Note:** The interface may list other tracks (e.g. NLP). Use **Python** or **Deep Learning** for the full supported experience in this release.

---

## 2. Before You Start

### What you need

- A modern web browser (Chrome, Edge, or Firefox recommended)
- Internet connection
- An account created on your institution’s SmartLearner instance

### Accessing the app

| Environment | Typical URL |
|-------------|-------------|
| Local development | `http://localhost:5173` (frontend) |
| Docker Compose | `http://localhost:8080` (frontend via nginx) |

The app talks to the backend API automatically (default: `http://localhost:8000` in development).

### Language

The landing page supports **English** and **Arabic** via the language control in the navigation bar. The dashboard is primarily in English.

---

## 3. Create an Account and Sign In

### Register

1. Open the home page and click **Register** (or go to `/register`).
2. Enter your **full name**, **email**, and **password**.
3. Submit the form.
4. After success, sign in with the same email and password.

### Sign in

1. Go to **Login** (`/login`).
2. Enter email and password.
3. You are redirected to the **Dashboard** (`/dashboard`).

### Your data is private per account

Progress, placement results, and syllabus are stored **per user**. If you share a computer, always **sign out** when finished (see [Settings](#12-settings-and-sign-out)).

---

## 4. Dashboard Overview

After login you see the main dashboard with a sidebar:

| Menu item | Purpose |
|-----------|---------|
| **Home** | Overview, shortcuts to start placement or generate syllabus |
| **Placement** | Adaptive level test |
| **Syllabus** | Your personalized course plan (modules and lessons) |
| **Lessons** | Read lessons, take quick assessments, track progress |
| **Exams** | Longer adaptive exams on a chosen lesson |
| **Analytics** | Mastery, progress, recommendations |
| **Q&A** | Ask questions about the current topic |
| **Settings** | Profile, theme, sign out |

A **rate limit banner** may appear if the AI service is busy; wait and try again.

---

## 5. Recommended Learning Path

Follow this order for the best experience:

```
Register / Login
    → Placement Test (choose track)
    → Generate Syllabus
    → Lessons (read → quiz → next lesson)
    → Q&A (optional, while studying)
    → Exams (optional, after studying a topic)
    → Analytics (review progress anytime)
```

You **must** complete placement before generating a syllabus. You **should** generate a syllabus before opening lessons.

---

## 6. Placement Test

**Path:** Dashboard → **Placement**

### Purpose

- Finds your starting **level** (beginner → very advanced)
- Records **strong** and **weak** concepts for later personalization

### How it works

1. Select your **track** (Python Foundations or Deep Learning).
2. Click **Start** (or equivalent) to begin.
3. Answer **one multiple-choice question at a time** (five questions per level stage).
4. After each answer, the next question loads automatically.

### Passing and advancing

- You need **at least 4 correct answers out of 5** on a level stage to **advance** to a harder stage.
- If you score below 4/5, the test **ends** and your **final level** is set from your performance.
- If you pass all stages, you may reach the highest level (**very advanced**).

### After the test

- View your **level**, **score**, **weak topics**, and **strong topics**.
- Go to **Syllabus** to generate your course (or use **Home** if it offers “Generate syllabus”).

---

## 7. Personalized Syllabus

**Path:** Dashboard → **Syllabus**

### Generate your syllabus

1. Complete placement first.
2. Click **Generate syllabus** (or it may auto-start when you arrive from placement).
3. Wait while the system builds modules and lessons (this uses AI and may take a minute).
4. When finished, you see **modules** (units) and **lessons** listed in order.

### What personalization means

- Topics you were **weak** on in placement may get **more** coverage in the plan.
- Topics you were **strong** on may stay **shorter** but still appear (required topics are not removed).

### Using the syllabus page

- Expand a module to see its lessons.
- Click **Start learning** (or open **Lessons**) to begin the first available lesson.
- An optional **PY4E outline** reference may appear for the Python track.

If generation fails, check your connection and try again, or complete placement if it was skipped.

---

## 8. Lessons and Quick Assessment

**Path:** Dashboard → **Lessons**

### Lesson list (left panel)

- Lessons are grouped by **module**.
- Icons show status:
  - **Open circle** — available
  - **Green check** — quiz passed
  - **Lock** — complete the previous lesson’s quiz first
  - **Warning** — attempted but not passed yet

A **progress bar** shows how many assessable lessons you completed in the course.

### Opening a lesson

1. Click an **unlocked** lesson in the sidebar.
2. The system **generates** lesson content the first time (markdown with headings, examples, and code).
3. Later visits load the **saved** content faster.

### Reading the lesson

- Scroll through objectives, explanations, examples, practice, and summary.
- Some lessons have **sub-lessons** (Part 1, Part 2, …) after remediation (see below).

### Quick assessment (lesson quiz)

1. When ready, click **Complete lesson and start assessment**.
2. Answer **5 multiple-choice questions**.
3. Submit your answers.

### Pass / fail rules

| Result | What happens |
|--------|----------------|
| **4 or 5 correct** | You **pass**. The next lesson unlocks. Analytics may update. |
| **Fewer than 4 correct** | You **fail**. The system may offer another quiz attempt or split the topic into **sub-lessons**. |
| **Sub-lessons** | Read each part; the quiz runs on the **final part only**. Passing it unlocks the next main lesson. |
| **Many failed attempts** | After repeated failure, the lesson may be **locked** until you review the material (message shown in the app). |

### After passing

- A success dialog may offer to go to the **next lesson**.
- Continue in order for the clearest path through the course.

---

## 9. Q&A Tutor

**Path:** Dashboard → **Q&A**

### Purpose

Ask questions about what you are studying. Answers are grounded in course material (not generic web search).

### How to use

1. Open a lesson first so the tutor knows your **current topic** (recommended).
2. Type your question in the chat box.
3. Send the message.
4. Read the formatted answer and optional **follow-up suggestions**.

### Tips

- Ask about concepts from your **current track** (Python or Deep Learning).
- Very off-topic questions may be refused with a message to stay within course scope.
- The tutor adapts explanation style to your level when mastery data is available.
- Chat history is saved **per user** in your browser for the session.

---

## 10. Exams

**Path:** Dashboard → **Exams**

### Prerequisites

- Complete **placement**
- Have a **syllabus** with at least one lesson

### How to take an exam

1. Select a **lesson** from the dropdown (from your syllabus).
2. Choose **number of questions** (3, 5, or 10) and difficulty if offered.
3. Generate the exam and answer all questions.
4. Submit to see your **score**, per-question feedback, and explanations.

### Notes

- Exams are **longer** than the quick lesson quiz.
- New attempts try to use **different question wording** than before.
- Weak topics from placement may appear more often.
- Passing threshold on the results screen is typically **60%** or higher (percentage shown after submit).

---

## 11. Analytics

**Path:** Dashboard → **Analytics**

### What you see

- **Overall progress** percentage through assessable lessons
- **Mastery** or topic strength (when enough activity exists)
- **Weak areas** and recommendations
- **Personal summary** and suggested **next actions** (continue, review, slow down, take a break)

### When data appears

- After **placement**, some placement metrics are available.
- After **lessons** and **quizzes**, progress and mastery update.
- Open Analytics anytime; if data is missing, complete placement and at least one lesson quiz first.

---

## 12. Settings and Sign Out

**Path:** Dashboard → **Settings**

- View your **profile** (name, email)
- Choose **avatar color**
- Toggle **light / dark** theme
- **Sign out** — clears your session; use this on shared devices

Signing out does not delete your account on the server; your courses and progress remain in the database.

---

## 13. Icons and Progress States

| Icon / state | Meaning |
|--------------|---------|
| Lock | Previous lesson quiz not passed yet |
| Green check | Lesson quiz passed |
| Open circle | Available, not yet completed |
| Warning / alert | Failed attempt; retry or open sub-lessons |
| Module progress % | Share of lessons completed in that unit |

---

## 14. Troubleshooting

| Problem | What to try |
|---------|-------------|
| Cannot log in | Check email/password; register if you have no account |
| “Complete placement first” | Finish Placement before Syllabus or Lessons |
| “Generate syllabus” disabled | Complete placement; refresh the page |
| Lesson shows **locked** | Pass the quiz on the previous lesson in order |
| Empty lesson / long loading | Wait; AI generation can take time. Refresh once. |
| API / AI errors | Wait a few minutes (rate limits). Try again later. |
| Wrong user’s data on same PC | Sign out, then sign in with your account |
| Q&A says off-topic | Rephrase using course vocabulary; open the relevant lesson first |
| Exam will not start | Ensure syllabus exists and a lesson is selected |

For technical setup (installing the app locally), see the root [README.md](../README.md) and [backend/SUPABASE-SETUP.md](../backend/SUPABASE-SETUP.md).

---

## 15. Quick Reference — URLs

| Page | Path |
|------|------|
| Home | `/` |
| Login | `/login` |
| Register | `/register` |
| Dashboard home | `/dashboard` |
| Placement | `/dashboard/placement` |
| Syllabus | `/dashboard/syllabus` |
| Lessons | `/dashboard/lessons` |
| Exams | `/dashboard/exams` |
| Analytics | `/dashboard/analytics` |
| Q&A | `/dashboard/qa` |
| Settings | `/dashboard/settings` |

---

## Document information

This guide describes the **student-facing** SmartLearner application. For developers (installation, API, architecture), see:

- [README.md](../README.md) — run locally or with Docker  
- Project report — Chapters 4 (Implementation) and 5 (Testing and Evaluation)

---

*SmartLearner — Adaptive multi-agent learning platform*
