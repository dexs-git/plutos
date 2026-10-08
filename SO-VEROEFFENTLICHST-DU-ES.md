# So veröffentlichst du Plutos auf GitHub + GitHub Pages

*(Diese Datei ist nur eine Anleitung für dich – du kannst sie nach dem
Veröffentlichen aus dem Repo löschen.)*

## 1. Repository anlegen und hochladen

1. Auf github.com einloggen → **New repository** → Name z. B. `plutos` →
   **Create repository** (ohne README/Lizenz anhaken, die liegen schon im
   Paket).
2. Dieses ZIP entpacken. Im entpackten Ordner (dort, wo `README.md` liegt):

```bash
git init
git add .
git commit -m "Plutos – Das Haushaltsbuch"
git branch -M main
git remote add origin https://github.com/DEIN-NUTZERNAME/plutos.git
git push -u origin main
```

## 2. GitHub Pages aktivieren

1. Im Repo auf GitHub: **Settings → Pages**
2. **Source:** *Deploy from a branch*
3. **Branch:** `main`, Ordner **`/docs`** → **Save**
4. Nach ca. 1–2 Minuten ist die Seite erreichbar unter
   `https://DEIN-NUTZERNAME.github.io/plutos/`

(Die Datei `docs/.nojekyll` ist bereits angelegt – sie verhindert, dass
GitHub die Seite durch Jekyll schickt.)

## 3. Download-Buttons mit Leben füllen

Die zwei Download-Buttons auf der Seite verweisen auf:

```
https://github.com/DEIN-NUTZERNAME/plutos/releases/latest/download/plutos-linux.zip
https://github.com/DEIN-NUTZERNAME/plutos/releases/latest/download/plutos-qt.zip
```

Damit sie funktionieren:

1. In `docs/index.html` **zweimal `DEIN-NUTZERNAME` ersetzen** (Suchen &
   Ersetzen) durch deinen echten GitHub-Nutzernamen – und, falls dein Repo
   nicht `plutos` heißt, auch den Repo-Namen.
2. Auf GitHub: **Releases → Draft a new release** → Tag z. B. `v1.0` →
   die beiden ZIPs (`gtk/` und `qt/` jeweils als ZIP gepackt) anhängen und
   **exakt** `plutos-linux.zip` bzw. `plutos-qt.zip` nennen → **Publish
   release**.

## 4. Lizenz nicht vergessen

Im `README.md` ganz unten steht ein Platzhalter für die Lizenz. Ohne
`LICENSE`-Datei dürfen andere den Code rechtlich gesehen weder nutzen noch
verändern. Eine einfache Option ist die MIT-Lizenz (auf GitHub: **Add file →
Create new file → Dateiname `LICENSE` → „Choose a license template“**).
