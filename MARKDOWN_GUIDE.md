# Markdown Guide

This project supports Markdown in several character sheet fields. This document explains how it works, which syntax is supported, and what gets stripped.

---

## How It Works

Markdown is rendered through a custom Jinja2 filter defined in `app/templates_config.py`.

**Pipeline:**

1. The raw text is parsed by [python-markdown](https://python-markdown.github.io/) with three extensions enabled: `tables`, `fenced_code`, and `nl2br`.
2. The resulting HTML is sanitized by [nh3](https://nh3.readthedocs.io/) — all tags and attributes not on the allowlist are stripped. No scripts, no event handlers, no inline styles.
3. The clean HTML is emitted in the template with `| safe`.

In templates the filter is applied like this:

```html
{{ field_value | markdown | safe }}
```

---

## Where Markdown Is Rendered

The following character sheet fields support Markdown:

| Section | Field |
|---|---|
| Features & Traits | Class Features |
| Features & Traits | Species Traits |
| Features & Traits | Feats |
| Attacks & Cantrips | Weapon / Cantrip notes |
| Spells | Spell notes |
| Equipment | Armor notes |
| Equipment | Throwable case item notes |
| Class Resources | Resource description |
| Bio | All long-text bio fields |

---

## Supported Syntax

### Headings

Only `h1`–`h4` survive sanitization. `h5` and `h6` are stripped (their text content is kept).

```markdown
# Heading 1
## Heading 2
### Heading 3
#### Heading 4
```

---

### Paragraphs & Line Breaks

The `nl2br` extension is active, so a **single newline** becomes a `<br>` — you do not need to add two spaces at the end of a line.

A blank line creates a new paragraph (`<p>`).

```markdown
First line
Second line (rendered on a new line due to nl2br)

New paragraph after the blank line.
```

---

### Emphasis

```markdown
**bold**           → <strong>
*italic*           → <em>
~~strikethrough~~  → <del>
```

---

### Inline Code & Code Blocks

Inline code with backticks:

```markdown
Use `Fireball` for the spell name.
```

Fenced code blocks (the `fenced_code` extension is active):

````markdown
```
1d6 fire damage per level
```
````

Indented code blocks (4 spaces) also work.

Both render as `<pre><code>…</code></pre>`.

---

### Blockquotes

```markdown
> *"Roll for initiative."*
```

---

### Lists

Unordered:

```markdown
- Dagger
- Shortsword
- Shield
```

Ordered:

```markdown
1. Choose a class
2. Assign ability scores
3. Pick a background
```

Nested lists work too.

---

### Horizontal Rule

```markdown
---
```

---

### Links

```markdown
[PHB reference](https://www.dndbeyond.com "D&D Beyond")
```

Only `href` and `title` attributes are kept on `<a>` tags. All other link attributes (e.g. `target`, `rel`) are stripped.

---

### Tables

The `tables` extension is active:

```markdown
| Spell | Level | Damage |
|-------|-------|--------|
| Fireball | 3 | 8d6 fire |
| Lightning Bolt | 3 | 8d6 lightning |
```

This renders a full `<table>` with `<thead>`, `<tbody>`, `<tr>`, `<th>`, and `<td>`.

---

## Allowed HTML Tags

Even if you write raw HTML inside a Markdown field it will be sanitized. Only the following tags survive:

| Category | Tags |
|---|---|
| Structure | `<p>`, `<br>`, `<hr>` |
| Headings | `<h1>`, `<h2>`, `<h3>`, `<h4>` |
| Inline text | `<strong>`, `<em>`, `<del>`, `<code>` |
| Blocks | `<pre>`, `<blockquote>` |
| Lists | `<ul>`, `<ol>`, `<li>` |
| Links | `<a>` (only `href` and `title` attributes) |
| Tables | `<table>`, `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>` |

### Allowed Attributes

Only one element may carry attributes:

| Tag | Allowed attributes |
|---|---|
| `<a>` | `href`, `title` |

Everything else — `id`, `class`, `style`, `target`, event handlers — is stripped from all tags.

---

## What Gets Stripped

The sanitizer silently removes anything not on the allowlist:

- Raw HTML tags like `<div>`, `<span>`, `<img>`, `<iframe>`, `<script>`, `<style>`, `<h5>`, `<h6>`, etc. (their text content is preserved where applicable)
- All attributes except `href` and `title` on `<a>`
- Inline styles (`style="…"`)
- CSS classes (`class="…"`)
- HTML IDs (`id="…"`)
- JavaScript event handlers (`onclick="…"`, etc.)
- `<h5>` and `<h6>` headings (text content is kept but the tag is removed)

---

## Quick Reference

```markdown
# H1 — ## H2 — ### H3 — #### H4
**bold**  *italic*  ~~strikethrough~~  `inline code`

- unordered list item
1. ordered list item

> blockquote

---   (horizontal rule)

[link text](https://url "optional title")

| Col A | Col B |
|-------|-------|
| cell  | cell  |

` `` `
fenced code block
` `` `
```
