<div align="center">

# 🧠 Second Brain — Autonomous AI Edge Skill

[![Version](https://img.shields.io/badge/version-3.3.0-blue?style=flat-square)](https://github.com/uussnn/second-brain/releases)
[![Model](https://img.shields.io/badge/model-Gemma--4--E4B--it-orange?style=flat-square&logo=google)](https://ai.google.dev/edge)
[![Platform](https://img.shields.io/badge/platform-AI_Edge_Gallery-4285F4?style=flat-square&logo=android)](https://github.com/google-ai-edge)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Privacy](https://img.shields.io/badge/privacy-100%25_on--device-darkgreen?style=flat-square)](SKILL.md)

**A self-evolving autonomous agent for Google AI Edge Gallery.**  
Runs fully offline. No cloud. No tracking. Just Gemma on your device.

[🇷🇺 Читать на русском](README.ru.md) · [📋 SKILL.md](SKILL.md) · [🐛 Report an Issue](https://github.com/uussnn/second-brain/issues)

</div>

---

## 🏆 Why Second Brain vs. Other Skills?

| Feature | Wikipedia Skill | Maps Skill | **Second Brain** |
|---|:---:|:---:|:---:|
| Multi-step autonomous planning | ❌ | ❌ | ✅ |
| Long-term personalized memory | ❌ | ❌ | ✅ |
| Self-evolving prompt (Meta AI) | ❌ | ❌ | ✅ |
| Goal Alignment | ❌ | ❌ | ✅ |
| Vision + Voice capture | ❌ | ❌ | ✅ |
| Community Capsule Sharing | ❌ | ❌ | ✅ |
| Works 100% offline | ✅ | ❌ | ✅ |

---

## ✨ Key Features

- **Agentic ReAct Workflow** — Thinks in steps: `Thought → Action (Tool) → Observation`. Reaches goals autonomously.
- **3-Layer Self-Evolution** — Personal corrections → Gene mutations → Meta-Prompt rewrites. The agent improves itself.
- **Memory Distillation** — Auto-compresses context after 100 events to prevent OOM on mobile chips.
- **Goal Alignment Framework** — Every new note is tested against your `goals.json`. Irrelevant info is deprioritized.
- **Evolution Map Dashboard** — Type `show dashboard` for an interactive Mermaid.js mutation tree and stats panel.
- **Safe Capsule Sharing** — Export insights (PII-stripped), import community knowledge with injection-safe validation.

---

## 🚀 Installation

### Option 1: Manual URL import (Recommended)
1. Open **Google AI Edge Gallery** on your Android/iOS device.
2. Tap **Agent Skills** → **Add Custom Skill** → **From URL**.
3. Paste this URL:
```
https://github.com/uussnn/second-brain
```
4. Confirm. The app will load and activate **Second Brain v3.3.0**.

### Option 2: Clone locally
```bash
git clone https://github.com/uussnn/second-brain.git
```
Point AI Edge Gallery to the local folder (see app documentation).

---

## 💬 Live Agent Response Example

Below is a real example of what Second Brain produces for the prompt:
> *"Review this week's newsletters and link any insights to my 'Business' goal."*

```
🧠 Second Brain (Autonomous) • 05 Apr 2026 🟢

### ✅ Agentic Steps Taken
→ Tool: read_gmail (7 newsletters fetched, 3 relevant flagged)
→ Tool: local_search "newsletter insight productivity"
→ Thought: 2 insights align with Goal: Business. Creating atomic notes.

### 🎯 Goal Alignment & MOC
• Goal Hit: [🎯 Business — +12 XP]
• Created: 2 atomic notes | Updated: [[MOC Productivity]]

### 📧 Gog Workspace Summary
• Digest: "Newsletter Digest — Week 14"
• Key insight: "High-ticket clients respond 3x better to voice notes"
• Calendar: Free slot found → Mon 17:00 (45 min) suggested for follow-up task

### 💡 Action Points
1. Record a voice note pitch for Client X — book Mon 17:00
2. Archive 4 low-signal newsletters → Digest-MOC

### 🧬 Evolution & Memory
**Personal Layer:** Verbosity preference held (Balanced)
**Meta:** No mutation triggered (queue: 4/8)
**Cache:** 34/100 events — healthy ✅

### ⚡ Quick Commands
• "show dashboard" • "rollback mutation" • "export capsule" • "compress memory"
```

---

## ⚡ Core Commands

Once the skill is active, try these to explore its capabilities:

**📊 Reviews & Planning**
- `"daily review"` / `"weekly review"`
- `"what's on my plate today"`

**🧠 Zettelkasten & Notes**
- `"MOC review"` / `"update MOCs"`
- `"show MOC [topic]"`
- `"save to Second Brain"` (to capture thoughts or images)

**🗂 Memory & Preferences**
- `"what did I say about [X]"`
- `"show my preferences"`
- `"add goal [your goal]"`

**🧬 Evolution & Maintenance**
- `"show dashboard"` (interactive Mermaid.js map)
- `"personal review"` (agent analyzes its own rules)
- `"compress memory"`
- `"export Capsule"` / `"import Capsule"`

**📧 Gog Workspace**
- `"triage my inbox"`
- `"check my calendar"`

---

## 🗂 Repository Structure

```text
second-brain/
├── SKILL.md                      # Core Agent System Prompt (v3.3.0)
├── README.md                     # This file (English)
├── README.ru.md                  # Russian version
└── Evolution/                    # Local data bootstraps (pre-seeded)
    ├── genes.json                # Agent behavior parameters
    ├── preferences.json          # User long-term memory (30–60 days)
    ├── capsules.json             # Atomic notes & community knowledge
    ├── events.jsonl              # Raw event log (auto-distilled at 100)
    ├── goals.json                # Your life goals (edit to personalize)
    └── evolution_history.jsonl   # Mutation changelog (for rollback)
```

---

## 🗺 Roadmap

- [x] v2.6 — GEP-lite + Personal Layer foundation
- [x] v2.8 — Evolution Map Dashboard (Mermaid.js)
- [x] v3.0 — Goal Alignment + Vision/Voice + Gog Toolkit
- [x] v3.1 — Capsule Sharing (Network-Evolution)
- [x] v3.2 — Memory Distillation (OOM protection)
- [x] **v3.3 — Autonomous Agentic Workflow (ReAct)** ← *You are here*
- [ ] v4.0 — Multi-Agent Swarm (Secretary, Researcher sub-skills)
- [ ] v4.1 — Gamification / Personal XP System

---

## 🤝 Contributing

Share your best community Capsules — open a Pull Request to `/capsules`.  
All capsules must pass local PII-strip and injection-check standards (see [SKILL.md](SKILL.md)).

---

<div align="center">
<sub>Built for offline Gemma-4-E4B-it inference on Google AI Edge Gallery · 100% private · No data leaves your device</sub>
</div>
