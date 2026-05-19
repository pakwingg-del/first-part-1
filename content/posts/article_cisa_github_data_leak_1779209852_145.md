---
title: "**CISA Finally Admits Their GitHub Was *Not* a \"Misconfigured Bucket\" – They Just Forgot the Password**"
date: 2026-05-19T16:57:32
persona_id: 5
persona_type: "Cynical Reddit user"
search_volume: "5000"
---

**CISA Finally Admits Their GitHub Was *Not* a "Misconfigured Bucket" – They Just Forgot the Password**

Oh great, another day, another *totally shocking* government data leak that definitely wasn't caused by someone clicking "paste" in the wrong terminal. The Cybersecurity and Infrastructure Security Agency (CISA), the very folks who tell *us* to use 2FA and patch our routers, just admitted they accidentally left a GitHub repository wide open to the public.

**The TL;DR:** CISA’s "CICADA" tool – a piece of software designed to hunt down malicious actors – apparently forgot to lock its own front door. A security researcher (not a state actor, just some dude with a VPN and too much time) found a repo containing API keys, database credentials, and what appears to be a spreadsheet labeled "Definitely Not Secret Vulnerabilities.xlsx."

**The Kick in the Teeth:** The data included access tokens to CISA’s own *internal* threat intelligence platforms. So, if you were a hacker, you could have literally logged in as CISA to see what CISA knows about you. AITA for finding this hilarious? Meanwhile, the official statement is basically: *"We take cybersecurity very seriously. We have rotated the credentials. Please ignore the sound of our admin facepalming through a wall."*

**The Real Punchline:** The leak was discovered on a Wednesday. They didn't fix it until Friday. Apparently, "See Something, Say Something" doesn't apply to government DevOps.

**Verdict:** CISA: "Do as we say, not as we accidentally hard-code into a public repo."