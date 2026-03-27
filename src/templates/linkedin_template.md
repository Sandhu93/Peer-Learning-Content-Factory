# LinkedIn Post Template

## Structure

Every LinkedIn post follows this exact structure:

---

**[HOOK — 1-2 lines]**
A pattern that trips up even senior engineers: [concept name].

[BLANK LINE — creates the "see more" break on mobile]

**[PROBLEM SETUP — 2-3 lines]**
Describe the failure mode. What goes wrong without this? Make it concrete and painful.

**[THE NAIVE APPROACH — 2-3 lines with code snippet or pseudo-code]**
```
# What most people write first
naive_code_here()
```
The problem: [one sentence on why naive fails]

**[THE INSIGHT — 1-2 lines]**
The key shift in thinking that unlocks the solution.

**[THE PRODUCTION APPROACH — 2-4 lines]**
```
# What production systems actually use
production_code_here()
```
This works because [one sentence rationale].

**[BUG STORY — 2-3 lines, optional but powerful]**
Real story: [brief what happened]. Lesson: [generalizable takeaway].

**[CALL TO ACTION — 1 line]**
What pattern have you seen trip up your team? Drop it in the comments.

**[HASHTAGS — 3-5 on final line]**
#SoftwareEngineering #BackendEngineering #SystemDesign #[ConceptSpecificTag]

---

## Writing Rules

1. **Hook is everything.** The first line must stop the scroll. Use: surprising stat, counterintuitive claim, "most engineers don't know X", or a relatable failure.
2. **No jargon without payoff.** Every technical term must earn its place by making the insight clearer.
3. **Code snippets should fit in 5 lines or fewer.** Anything longer gets skipped.
4. **Concrete > abstract.** "Your service crashed at 3am because of this" > "This is important for reliability."
5. **Character limit:** 2,800 characters max for full visibility.
6. **Emojis:** Use sparingly — maximum 3, only if they add visual chunking.
7. **Blank lines:** Use between each major section to improve readability on mobile.

## Example

---

A pattern that trips up senior engineers: the thundering herd.

Your cache expires at exactly midnight. 10,000 requests hit the database simultaneously. It falls over. This happens every single day in high-traffic systems — and it's almost always preventable.

Here's what most systems do:

```python
def get_user(user_id):
    cached = cache.get(user_id)
    if not cached:
        cached = db.query(user_id)  # 10k of these at once = 💥
        cache.set(user_id, cached, ttl=3600)
    return cached
```

The problem: when the key expires, every waiter rushes the kitchen at once.

The fix is a mutex lock per cache key:

```python
def get_user(user_id):
    cached = cache.get(user_id)
    if not cached:
        with lock(f"rehydrate:{user_id}", timeout=5):
            cached = cache.get(user_id)  # check again inside lock
            if not cached:
                cached = db.query(user_id)
                cache.set(user_id, cached, ttl=3600)
    return cached
```

Only one thread rehydrates the cache. The rest wait, then read from the freshly-filled cache.

We hit this at 2am on Black Friday. The on-call engineer who added the mutex lock became a legend.

What's the most expensive cache bug you've debugged? Share below.

#SoftwareEngineering #BackendEngineering #SystemDesign #CacheStampede
