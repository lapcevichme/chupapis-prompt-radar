Here is the detailed summary of the case pitch **"Prompt-Radar"** by **CROC** (brainz division), presented during the hackathon.

The presentation focuses on creating an automated analytics system for user queries made to internal AI agents.

### 1. Context and Problematics (Business "Pain Points")

* **The AI Boom:** CROC, like many other companies, is actively implementing generative AI. Employees have been given carte blanche to use various AI services and agents.
* **Unclear ROI:** Management sees that context (and the token budget) is being consumed at a colossal rate, but asks the critical question: *what is the real, digitized impact on the business?*
* **The "Hidden Knowledge" Problem:** The speaker gives an example of an employee who used AI to reduce meeting preparation time from 1 hour to 5 minutes, but refuses to share this skill with colleagues, considering it a personal competitive advantage.
* **Inefficiency of Manual Labor:** Manually analyzing query logs takes weeks and is highly subjective. The business needs a tool that translates the "noise of logs into clear decisions."

### 2. Main Task for Participants

The core objective is to develop a system that automatically evaluates the real-world usefulness of an AI tool.

**Key Functionality (Must-have):**

1. **Classification:** Assigning a category or tag to each user query (based on topics and task types).
2. **Finding Use-Cases:** Discovering stable patterns of AI agent usage and grouping similar queries together.
3. **Summarization:** Creating a concise breakdown of these scenarios (e.g., what is asked most often, what the typical formulations are, and where the potential for further automation lies).
4. **Visualization:** Producing a clear, understandable report or dashboard for top management (a table, web page, dashboard, etc.) that illustrates what is happening with AI in the company and how to develop the platform further.

**Bonus Task (Task with an asterisk):**

* Tracking erroneous LLM responses (hallucinations, Out of Memory crashes, agent glitches). Identifying exactly which queries "break" the system.

### 3. Calculation Methodology (Highest Priority)

The speaker emphasizes that writing the script is only a fraction of the work. The main challenge is to **invent the methodology and algorithm for evaluating efficiency itself**.

* Participants must consider that AI agents are integrated into a vast internal infrastructure: email, ticketing systems (Atlassian/Jira), internal Wikis, HR services, etc.
* The final metric should accurately reflect the reduction in time spent by employees and, ultimately, the savings in FTE (Full-Time Equivalent) and the payroll fund.

### 4. Business Goal of the Project

* CROC employs a *"dogfooding"* approach: products are first developed and tested internally.
* If the developed tool demonstrates high efficiency (a "wow effect") and successfully digitizes the benefits of AI for top management, **the system will be packaged into a standalone product and sold to external clients** (enterprise companies facing the exact same AI implementation hurdles).

### 5. Technical Requirements and Submission Format

* **Technologies:** Absolute freedom in choosing technologies and architecture.
* **Limitations:** Must use the specified GPU pool (H100).
* **Submission Format:**
1. A repository containing the code and launch instructions.
2. An input dataset (or a script to generate/load it).
3. A final report/dashboard (Markdown, PDF, Streamlit, Gradio, or web interface).


* **Defense (Pitching):** The evaluation consists of a two-stage defense — technical (code review) and presentation (defending the business vision). The speaker stresses that effectively "selling" the business value of the solution is just as important as writing the code.