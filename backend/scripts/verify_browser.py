"""Skrip verifikasi browser otomatis (Playwright + Chrome) untuk mobile, tablet, dan desktop."""
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"


def run_browser_checks() -> None:
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for width, height, label in [(375, 812, "mobile"), (768, 1024, "tablet"), (1280, 800, "desktop")]:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on(
                "console",
                lambda msg, lbl=label: errors.append(f"[{lbl}] console.{msg.type}: {msg.text}")
                if msg.type == "error"
                else None,
            )
            page.on("pageerror", lambda exc, lbl=label: errors.append(f"[{lbl}] pageerror: {exc}"))

            page.goto(BASE_URL, wait_until="networkidle")
            page.wait_for_selector("#matches-tbody tr")
            overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
            assert not overflow, f"Horizontal overflow terdeteksi pada {label} ({width}x{height})"

            footer_text = page.locator("footer").inner_text()
            assert "Perjudian dilarang di Indonesia" in footer_text, f"Footer disclaimer hilang pada {label}"
            print(f"[OK] {label} ({width}x{height}): matches loaded, overflow={overflow}")

            if label == "desktop":
                for tab in ["tab-standings", "tab-simulator", "tab-history", "tab-methodology", "tab-design-system", "tab-dashboard"]:
                    page.click(f"#{tab}")
                    page.wait_for_timeout(400)

                page.locator("#matches-tbody button:has-text('Detail')").first.click()
                page.wait_for_selector("#detail-content h2")

                page.click("#tab-dashboard")
                page.wait_for_timeout(300)
                page.locator("#matches-tbody button:has-text('+ Sim')").nth(0).click()
                page.click("#tab-dashboard")
                page.wait_for_timeout(200)
                page.locator("#matches-tbody button:has-text('+ Sim')").nth(1).click()
                page.wait_for_selector("#sim-result strong")

                sim_text = page.locator("#view-simulator").inner_text()
                assert "Perjudian dilarang di Indonesia" in sim_text, "Simulator disclaimer hilang"

                # Cek Light & Dark mode toggle
                page.click("#btn-theme")
                is_dark = page.evaluate("document.documentElement.classList.contains('dark')")
                assert is_dark is False, "Light mode gagal aktif"
                page.click("#btn-theme")

                # Cek tombol Sinkronkan Data
                page.click("#tab-dashboard")
                page.click("#btn-sync-now")
                page.wait_for_function(
                    "document.getElementById('sync-status-bar').innerText.includes('Sinkronisasi selesai')",
                    timeout=25000,
                )
                print("[OK] Semua tab, detail laga, simulator 2-leg, tombol Sinkronkan Data, dan toggle Light/Dark terverifikasi!")

            page.close()
        browser.close()

    print(f"Total Console/Page Errors: {len(errors)}")
    for e in errors:
        print("ERR:", e)
    assert len(errors) == 0, f"Ditemukan error console/page: {errors}"


if __name__ == "__main__":
    run_browser_checks()
