# Reel Script Template

## Format

Total duration: 60 seconds
Scenes: 5-7 scenes, each 8-15 seconds
Tone: Direct, punchy, slightly urgent — like a senior engineer explaining to a junior one
Visual style: Code on dark background, state diagrams, simple animations

---

## Scene Structure

Each scene entry:

```
[TIMESTAMP] SCENE TITLE
Voiceover: "..."
Visual: [description of what's on screen]
```

---

## Scene Types

| Scene | Purpose | Duration |
|-------|---------|----------|
| Hook | Stop the scroll. Name the problem. | 5-8s |
| Pain | Show the failure. Make it concrete. | 8-12s |
| Naive code | Show what people actually write | 8-10s |
| Insight | The mental model shift | 5-8s |
| Solution code | The production pattern | 10-12s |
| Proof | Test, metric, or outcome that confirms it works | 6-8s |
| CTA | Ask a question to drive comments | 3-5s |

---

## Example Script

---

**[0:00–0:07] THE HOOK**
Voiceover: "Your retry logic might be making your outage worse."
Visual: Red alert notification flooding a dashboard. Counter spinning up.

---

**[0:07–0:18] THE PAIN**
Voiceover: "When a service goes down, naive retry code slams it with thousands of requests per second — all at the exact same interval. The service never gets a chance to recover."
Visual: Timeline diagram — service goes down at T=0, wave of identical requests at T=1, T=2, T=3.

---

**[0:18–0:28] THE NAIVE CODE**
Voiceover: "This is what most people write first."
Visual: Code editor, dark background:
```python
for attempt in range(3):
    try:
        return call_api()
    except Exception:
        time.sleep(1)  # fixed 1 second for everyone
```
Voiceover: "Every caller waits exactly one second. And tries again. At the same time."

---

**[0:28–0:36] THE INSIGHT**
Voiceover: "The fix is two things: exponential backoff, plus jitter."
Visual: Formula appears: `wait = base^attempt + random(0, base)`
Voiceover: "Space out the retries. Then randomize them."

---

**[0:36–0:50] THE SOLUTION**
Voiceover: "Here's what production looks like."
Visual: Code editor:
```python
import random, time

def retry_with_backoff(fn, base=1, max_wait=30):
    for attempt in range(5):
        try:
            return fn()
        except Exception:
            wait = min(base * (2 ** attempt), max_wait)
            time.sleep(wait + random.uniform(0, base))
```
Voiceover: "Exponential growth caps the wait. Jitter spreads the load across the retry window."

---

**[0:50–0:57] THE PROOF**
Voiceover: "In testing: fixed interval retries hit the recovering service at 800 RPS. With jitter: under 50."
Visual: Bar chart comparing retry traffic. Fixed: tall red bar. Jittered: flat green bars.

---

**[0:57–1:00] CTA**
Voiceover: "What's the most expensive retry bug you've seen? Drop it below."
Visual: Comment prompt with question on screen.

---

## Writing Rules

1. **Every scene needs both voiceover AND visual.** The visual must reinforce the words, not just echo them.
2. **Code snippets max 8 lines.** If it doesn't fit, it's too complex for a reel.
3. **No more than one concept per scene.** One idea, one visual, one piece of narration.
4. **The hook must name a specific failure, not a generic topic.** "Your retry logic might be making your outage worse" > "Let's talk about retries."
5. **The CTA must ask a specific question** that invites engineers to share their own experience.
6. **Timestamps are approximate** — adjust during editing.
