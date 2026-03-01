# i18n Implementation Guide

## Setup Complete! ✅

Your app now supports English and Russian translations. Here's what was added:

### 1. Database Changes
- Added `language` field to User model (default: "en")
- Created migration `007_add_user_language.py`
- Language is stored in user session for fast access

### 2. Translation Files
- English: `app/locales/en/LC_MESSAGES/messages.po`
- Russian: `app/locales/ru/LC_MESSAGES/messages.po`

### 3. Settings Page
- Users can change language at `/settings`
- Settings are saved to database and update the session

---

## How to Use

### Step 1: Run Migration
```bash
docker exec -it dnd_app alembic upgrade head
```

### Step 2: Compile Translations
```bash
python compile_translations.py
```

Or manually:
```bash
msgfmt app/locales/en/LC_MESSAGES/messages.po -o app/locales/en/LC_MESSAGES/messages.mo
msgfmt app/locales/ru/LC_MESSAGES/messages.po -o app/locales/ru/LC_MESSAGES/messages.mo
```

### Step 3: Update Your Handlers

**OLD WAY:**
```python
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

@router.get("/example")
async def example(request: Request, current_user: UserSession = Depends(require_login)):
    return templates.TemplateResponse("example.html", {
        "request": request,
        "current_user": current_user,
    })
```

**NEW WAY (with translations):**
```python
from fastapi.templating import Jinja2Templates
from app.i18n import render_template  # Add this import

templates = Jinja2Templates(directory="app/templates")

@router.get("/example")
async def example(request: Request, current_user: UserSession = Depends(require_login)):
    return render_template(
        templates,
        "example.html",
        {
            "request": request,
            "current_user": current_user,
        },
        language=current_user.language,  # Use user's language preference
    )
```

### Step 4: Update Templates

Wrap any text you want to translate with `{{ _("text") }}`:

**Before:**
```html
<h1>Characters</h1>
<button>Save</button>
<p>Character Name</p>
```

**After:**
```html
<h1>{{ _("Characters") }}</h1>
<button>{{ _("Save") }}</button>
<p>{{ _("Character Name") }}</p>
```

---

## Adding New Translations

1. **Add to both .po files:**

   Edit `app/locales/en/LC_MESSAGES/messages.po`:
   ```
   msgid "My New String"
   msgstr "My New String"
   ```

   Edit `app/locales/ru/LC_MESSAGES/messages.po`:
   ```
   msgid "My New String"
   msgstr "Моя новая строка"
   ```

2. **Recompile:**
   ```bash
   python compile_translations.py
   ```

3. **Restart the app**

---

## Translation Functions Available in Templates

- `_("text")` - Translate text (shorthand)
- `gettext("text")` - Translate text (full name)
- `ngettext("singular", "plural", count)` - Plural forms

---

## Example: Update character_handler.py

```python
# At the top, add:
from app.i18n import render_template

# Then update each route:
@router.get("", response_class=HTMLResponse)
async def character_list(
    request: Request,
    current_user: UserSession = Depends(require_dm),
    service: CharacterService = Depends(_service),
):
    characters = await service.list_all()
    return render_template(
        templates,
        "characters/list.html",
        {
            "request": request,
            "current_user": current_user,
            "characters": characters,
        },
        language=current_user.language,
    )
```

---

## Notes

- The `_()` function is automatically available in all templates when using `render_template()`
- For unauthenticated pages (like login), use `language="en"` as default
- All existing functionality remains unchanged if you don't use translations
- The navbar already has translation support with fallbacks
