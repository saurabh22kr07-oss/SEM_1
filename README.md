# Quizzy Pro — Modern Interactive Quiz Platform

A full-stack, production-ready interactive quiz web application built with **Python Flask** and **SQLite**.

---

## ✨ Key Features

### 1. 🎓 Separate Student & Admin Login Portals
- **Student Login Portal (`/login`)**:
  - Dedicated student access.
  - Sign in using either an **email address** or **10-digit mobile number**.
  - 1-click demo credential autofill.
  - Automatic redirect to student quizzes.
- **Administrator Control Portal (`/admin/login`)**:
  - Dedicated security portal with elevated dark/shield styling.
  - Strict role enforcement (student credentials rejected with clear access warnings).
  - 1-click admin demo credential autofill.
  - Direct access to quiz authoring, attendee analytics, and student helpdesk.

### 2. 💬 Helpdesk & Student Support Center
- **Student View (`/helpdesk`)**:
  - Raise support queries regarding quizzes, scores, questions, or accounts.
  - Pre-fills student name and email when logged in.
  - Category tags (Quiz Issue, Grading & Scores, Account & Login, Suggestions).
  - **"My Support Tickets"** tracking: Live status badges (**Open**, **In Progress**, **Resolved**) with official replies from instructors.
- **Admin Management (`/admin/helpdesk`)**:
  - Real-time ticket counter in navbar with pending badges.
  - Filter tickets by status (All, Open, Resolved).
  - Inline response editor to write verified answers and mark queries as resolved.
  - Ticket deletion action.

### 3. 👥 Live Attendee Tracking ("Show student ki kiti janani pahile ti quiz attend keli aahe")
- **Home Page Quiz Cards**:
  - Displays verified attendance counters: `👥 X students attended (Y total attempts)`.
  - Category tags (`Programming`, `Web Dev`, `Science & Tech`, `AI & Data`) and difficulty tags (`Easy`, `Medium`, `Hard`).
  - Search bar and category filter pills.
- **Quiz Header Banner**:
  - High-visibility social proof banner showing exactly how many students have completed the test before you start.
- **Results & Admin View**:
  - Displays student attempt order (`You are student #X to complete this quiz!`) and full attendee metrics in admin reports.

### 4. 📖 Detailed Question Review & Concept Explanations
- **Immediate Feedback on Submission**:
  - Full question breakdown showing what the student chose vs. the correct answer.
  - Color-coded choices: Green check for correct, Red cross for incorrect.
  - **Concept Explanations**: Clear, pedagogical explanations explaining *why* the answer is correct.
- **Attempt History Review (`/review/<attempt_id>`)**:
  - Revisit any past attempt from `/history` to review previous answers and explanations anytime.

### 5. 🛡️ Admin Control & Reporting
- Create, edit, and delete quizzes.
- Add questions with multiple-choice options and concept explanations.
- Remove questions with 1-click confirmation.
- 📥 **Export to CSV**: Download complete student performance reports in CSV format with scores, percentages, and timestamps.
- Search and filter student submissions.

---

## 🚀 How to Run

1. Open this project folder in your terminal or VS Code:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Start the Flask application:
   ```powershell
   python app.py
   ```

3. Open your browser and navigate to:
   ```
   http://127.0.0.1:5000
   ```

---

## 🔑 Demo Accounts

### 🎓 Student Login (`/login`)
- **Email:** `student@quizzy.com`
- **Mobile:** `9876543210`
- **Password:** `Student@123`
*(You can also register a new student account at `/register` using any email or 10-digit mobile number!)*

### 🛡️ Admin Portal (`/admin/login`)
- **Email:** `admin@quizzy.com`
- **Password:** `Admin@123`
