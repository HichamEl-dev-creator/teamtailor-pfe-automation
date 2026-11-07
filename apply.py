#!/usr/bin/env python3
"""Teamtailor PFE helper. Dry run by default; explicit --submit for real applications.

Selectors are based on visible French labels, NOT verified DOM attributes.
Respect site policies, manual CAPTCHA and submission limits.
"""
import argparse
import csv
import json
import random
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = 'https://ytdvincienergiesafriqueouest.teamtailor.com'
JOBS = BASE + '/jobs'
ROOT = Path(__file__).resolve().parent
LOG = ROOT / 'candidatures.csv'
SHOTS = ROOT / 'captures'
FIELDS = ['date', 'url', 'titre', 'statut', 'detail']


def delay(low=1.5, high=3.0):
    """Polite pacing (not intended to bypass a site's anti-bot controls)."""
    time.sleep(random.uniform(low, high))


def log(url, title, status, detail=''):
    new = not LOG.exists()
    with LOG.open('a', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(dict(date=datetime.now().isoformat(timespec='seconds'), url=url,
                        titre=title, statut=status, detail=str(detail)[:500]))
    print(f'[{status}] {title}: {detail}')


def previously_sent():
    if not LOG.exists():
        return set()
    with LOG.open(encoding='utf-8', newline='') as f:
        return {r['url'] for r in csv.DictReader(f) if r['statut'] == 'soumis'}


def first_visible(*locators):
    for loc in locators:
        try:
            for i in range(min(loc.count(), 12)):
                candidate = loc.nth(i)
                if candidate.is_visible():
                    return candidate
        except Exception:
            pass
    return None


def job_links(page):
    """Scroll and click 'Afficher 20 de plus' as long as it exists."""
    page.goto(JOBS, wait_until='domcontentloaded', timeout=45000)
    delay()
    dismiss_cookies(page)
    last_count = -1
    for _ in range(40):
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        delay(0.7, 1.4)
        more = first_visible(page.get_by_text(re.compile(r'afficher\s+\d+\s+de\s+plus', re.I)),
                             page.get_by_role('button', name=re.compile(r'afficher|plus|load more', re.I)))
        anchors = page.locator('a[href*="/jobs/"]')
        count = anchors.count()
        if more is None:
            if count == last_count:
                break
            last_count = count
            continue
        try:
            more.click(timeout=6000)
        except Exception:
            break
        last_count = count

    data = page.locator('a[href*="/jobs/"]').evaluate_all('''els => els.map(a => ({
        url: a.href.split('#')[0].split('?')[0], title: (a.innerText || '').trim()
    }))''')
    unique = {}
    for entry in data:
        url = entry['url']
        parsed = urlparse(url)
        if parsed.netloc == urlparse(BASE).netloc and re.search(r'/jobs/\d+', parsed.path):
            unique.setdefault(url, entry['title'] or parsed.path.rsplit('/', 1)[-1])
    return list(unique.items())


def dismiss_cookies(page):
    for label in [r'Refuser les cookies facultatifs', r'Refuser', r'Accepter tous les cookies']:
        button = first_visible(page.get_by_role('button', name=re.compile(label, re.I)))
        if button:
            try:
                button.click(timeout=3000)
                return
            except Exception:
                pass


def contexts(page):
    # Teamtailor may render the application form inside an iframe.
    return [page] + [frame for frame in page.frames if frame != page.main_frame]


def find_field(page, labels, css=None):
    for context in contexts(page):
        candidates = []
        for label in labels:
            regex = re.compile(label, re.I)
            candidates.extend([context.get_by_label(regex), context.get_by_placeholder(regex)])
        if css:
            candidates.append(context.locator(css))
        match = first_visible(*candidates)
        if match:
            return match
    return None


def fill_required(page, labels, value, css=None, mandatory=True):
    loc = find_field(page, labels, css)
    if not loc:
        if mandatory:
            raise RuntimeError('Champ introuvable : ' + '/'.join(labels))
        return False
    loc.fill(str(value))
    return True


def radio(page, question_pattern, answer, mandatory=True):
    """Choose a radio by clicking its visible label/wrapper.

    Some Teamtailor themes visually hide the input itself, so locator.check()
    can time out even though the input has been resolved correctly.
    """
    expected = re.compile(r'^' + re.escape(answer) + r'$', re.I)

    def activate(candidate, ctx):
        try:
            if candidate.is_checked():
                return True
        except Exception:
            pass
        try:
            identity = candidate.get_attribute('id', timeout=1500)
            if identity:
                label = ctx.locator('label[for="' + identity + '"]')
                if label.count() and label.first.is_visible():
                    label.first.click(timeout=3000)
                    if candidate.is_checked():
                        return True
            # Radio may be nested inside a label (clickable wrapper).
            wrapping_label = candidate.locator('xpath=ancestor::label[1]')
            if wrapping_label.count() and wrapping_label.first.is_visible():
                wrapping_label.first.click(timeout=3000)
                if candidate.is_checked():
                    return True
            # Fallback: click actual radio only if interactable.
            candidate.check(timeout=3000)
            return candidate.is_checked()
        except Exception as exc:
            print(f'Option {answer}: tentative impossible ({type(exc).__name__})')
            return False

    for ctx in contexts(page):
        question = first_visible(ctx.get_by_text(re.compile(question_pattern, re.I)))
        containers = []
        if question:
            containers = [question.locator(x) for x in
                          ['xpath=..', 'xpath=../..', 'xpath=../../..']]
        containers.append(ctx)
        for index, container in enumerate(containers):
            radios = container.get_by_role('radio', name=expected)
            if index == len(containers) - 1 and radios.count() != 1:
                continue
            for i in range(min(radios.count(), 8)):
                if activate(radios.nth(i), ctx):
                    print(f'Option radio sélectionnée : {answer}')
                    return True
    if mandatory:
        raise RuntimeError(f'Choix radio {question_pattern} / {answer} impossible')
    print(f'Choix facultatif non sélectionné : {answer}')
    return False


def school(page, label):
    """Select the FST option from native or custom school dropdowns."""
    target = re.compile(r"\bFST\b", re.I)
    for ctx in contexts(page):
        field = first_visible(
            ctx.get_by_label(re.compile(r"Quel est ton école|Quelle est ton école|École", re.I)),
            ctx.get_by_role('combobox', name=re.compile(r'école', re.I)),
            ctx.locator('select').filter(has=ctx.locator('option', has_text=target)),
        )
        if field is None:
            # Fallback to visible combobox when its accessible name is missing.
            field = first_visible(ctx.get_by_role('combobox'), ctx.locator('select'))
        if field is None:
            continue
        tag = field.evaluate('(el) => el.tagName.toLowerCase()')
        if tag == 'select':
            options = field.locator('option').all_text_contents()
            found = next((name for name in options if target.search(name)), None)
            if found:
                field.select_option(label=found)
                print(f'École sélectionnée : {found}')
                return
            continue
        field.click()
        option = first_visible(
            ctx.get_by_role('option', name=target),
            ctx.get_by_text(target),
        )
        if option is None:
            try:
                field.fill('FST')
            except Exception:
                search = first_visible(ctx.get_by_role('textbox', name=re.compile('recherch', re.I)))
                if search:
                    search.fill('FST')
            option = first_visible(ctx.get_by_role('option', name=target), ctx.get_by_text(target))
        if option is not None:
            option.click()
            print('École sélectionnée : FST')
            return
    raise RuntimeError("Option FST introuvable dans la liste des écoles.")


def upload(page, file_path, type_hint, required=True):
    """Find file inputs by accept/name or proximity to visible upload wording."""
    path = Path(file_path).expanduser().resolve() if file_path else None
    if not path or not path.is_file():
        if required:
            raise FileNotFoundError(f'{type_hint}: fichier manquant : {file_path}')
        return False
    for ctx in contexts(page):
        inputs = ctx.locator('input[type="file"]')
        candidate = None
        for i in range(inputs.count()):
            element = inputs.nth(i)
            props = element.evaluate('el => ({accept: el.accept || "", name: el.name || "", id: el.id || "", outer: el.outerHTML.slice(0,400)})')
            info = ' '.join(str(v) for v in props.values()).lower()
            if type_hint == 'video' and 'video' in info:
                candidate = element
                break
            if type_hint == 'cv' and any(k in info for k in ['resume', 'cv', 'pdf', 'document']):
                candidate = element
                break
        if not candidate:
            # Anchor to the label displayed in screenshot and find the nearest file input.
            label_regex = r'Importer vidéo|Import.*vidéo' if type_hint == 'video' else r'Importer un CV|CV\s*\*'
            marker = first_visible(ctx.get_by_text(re.compile(label_regex, re.I)))
            if marker:
                for parent in ['xpath=..', 'xpath=../..', 'xpath=../../..', 'xpath=../../../..']:
                    root = marker.locator(parent)
                    options = root.locator('input[type="file"]')
                    if options.count() == 1:
                        candidate = options.first
                        break
        if candidate:
            candidate.set_input_files(str(path))
            return True
        # For an import button which opens file chooser, no selector for input is needed.
        button = first_visible(ctx.get_by_role('button', name=re.compile('Importer vidéo' if type_hint == 'video' else 'Importer un CV', re.I)))
        if button:
            try:
                with page.expect_file_chooser(timeout=3500) as chooser:
                    button.click()
                chooser.value.set_files(str(path))
                return True
            except PWTimeout:
                pass
    if required:
        raise RuntimeError(f'Entrée fichier {type_hint} introuvable : inspection HTML nécessaire')
    return False


def open_application(page):
    for ctx in contexts(page):
        btn = first_visible(ctx.get_by_role('button', name=re.compile(r'^Postuler$', re.I)),
                            ctx.get_by_role('link', name=re.compile(r'^Postuler$', re.I)),
                            ctx.get_by_text(re.compile(r'^Postuler$', re.I)))
        if btn:
            btn.click(timeout=8000)
            delay(1, 2)
            return
    raise RuntimeError('Bouton Postuler introuvable')


def has_captcha(page):
    for ctx in contexts(page):
        try:
            if ctx.locator('iframe[src*="captcha"], iframe[src*="recaptcha"], [class*="captcha"], [id*="captcha"]').count():
                return True
        except Exception:
            continue
    return False


def do_form(page, profile):
    radio(page, r'recherche d.un stage de PFE', 'Oui')
    school(page, profile['ecole'])
    fill_required(page, [r'intitulé de ta formation', r'intitulé de.*formation'], profile['formation'])
    fill_required(page, [r'Quelles langues parles-tu', r'langues'], profile['langues'], mandatory=False)
    radio(page, r'Tu es\s*\?', profile['Genre'], mandatory=False)
    fill_required(page, [r'^Prénom'], profile['prenom'], css='input[autocomplete="given-name"]')
    fill_required(page, [r'^Nom\s*\*?$', r'^Nom$'], profile['nom'], css='input[autocomplete="family-name"]')
    fill_required(page, [r'E-?mail', r'Adresse e-?mail'], profile['email'], css='input[type="email"]')
    fill_required(page, [r'Téléphone', r'phone'], profile['telephone'], css='input[type="tel"]')
    upload(page, profile['cv'], 'cv')
    upload(page, profile['video'], 'video')
    if profile.get('motivation'):
        fill_required(page, [r'Lettre de motivation'], profile['motivation'],
                      css='textarea[name*="cover_letter"]', mandatory=False)
    # Observe any other questions with required indicators before submitting.


def submission_button(page):
    for ctx in contexts(page):
        button = first_visible(ctx.get_by_role('button', name=re.compile(r'Envoyer ma candidature|Soumettre ma candidature|Send application', re.I)),
                               ctx.locator('button[type="submit"]'))
        if button:
            return button
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(ROOT / 'profil.json'))
    parser.add_argument('--submit', action='store_true', help='Autorise les envois réels (sinon test seulement)')
    parser.add_argument('--limit', type=int, default=0, help='Nombre maximum d\'offres traitées, 0 = toutes')
    parser.add_argument('--all-offers', action='store_true', help='Inclure toutes les offres (sinon filtre de pertinence)')
    parser.add_argument('--headless', action='store_true', help='Sans fenêtre, déconseillé pour CAPTCHA')
    args = parser.parse_args()
    profile = json.loads(Path(args.config).read_text(encoding='utf-8'))
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=args.headless)
        context = browser.new_context(locale='fr-FR', viewport={'width': 1366, 'height': 900})
        page = context.new_page()
        offers = job_links(page)
        print(f'{len(offers)} offres uniques découvertes')
        (ROOT / 'offres.json').write_text(json.dumps(offers, ensure_ascii=False, indent=2), encoding='utf-8')
        if not args.all_offers:
            terms = ['informatique', 'logiciel', 'développ', 'data', 'donnée', 'intelligence artificielle',
                     ' ia ', 'digital', 'vidéo intelligente', 'cybersécurité', 'cloud', 'réseau', 'système d’information',
                     'bim', 'application', 'tracking']
            offers = [(u, t) for u, t in offers if any(k in (' ' + t.casefold() + ' ') for k in terms)]
            print(f'{len(offers)} offres retenues après filtrage par titre')
        already = previously_sent()
        count = 0
        for url, title in offers:
            if url in already:
                log(url, title, 'ignoré', 'Déjà soumis dans le journal')
                continue
            if args.limit and count >= args.limit:
                break
            count += 1
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=45000)
                dismiss_cookies(page)
                delay()
                open_application(page)
                do_form(page, profile)
                page.screenshot(path=str(SHOTS / f'offre_{count}_previsualisation.png'), full_page=True)
                if has_captcha(page):
                    if args.headless:
                        raise RuntimeError('CAPTCHA détecté : relancer sans --headless')
                    print('CAPTCHA détecté : le résoudre manuellement dans le navigateur.')
                    input('Appuyer sur Entrée une fois résolu, ou Ctrl+C pour arrêter : ')
                if not args.submit:
                    log(url, title, 'test', 'Formulaire rempli, AUCUN ENVOI')
                    continue
                button = submission_button(page)
                if not button:
                    raise RuntimeError('Bouton de soumission introuvable')
                button.click(timeout=10000)
                delay(2, 4)
                # A click alone is not proof of submission. Verify confirmation text.
                confirmation = False
                for ctx in contexts(page):
                    message = first_visible(ctx.get_by_text(re.compile(
                        r'candidature (a bien été envoyée|envoyée|reçue)|merci pour (ta|votre) candidature|application (submitted|received)|thank you for applying', re.I)))
                    if message:
                        confirmation = True
                        break
                if confirmation:
                    log(url, title, 'soumis', 'Confirmation affichée')
                    already.add(url)
                else:
                    page.screenshot(path=str(SHOTS / f'offre_{count}_a_verifier.png'), full_page=True)
                    log(url, title, 'à vérifier', 'Clic effectué, aucune confirmation reconnue — vérifier manuellement')
                    # Avoid duplicate submissions while a status is uncertain.
                    print('Statut incertain : arrêt pour éviter les doublons.')
                    break
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                try:
                    page.screenshot(path=str(SHOTS / f'offre_{count}_erreur.png'), full_page=True)
                except Exception:
                    pass
                log(url, title, 'erreur', repr(exc))
            delay(4, 7)
        browser.close()


if __name__ == '__main__':
    main()
