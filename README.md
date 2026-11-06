# Desktop Timer ⏱️

Windows 11 Virtuális Asztal-érzékeny (Virtual Desktop-aware), minimalista lebegő munkaidő mérő alkalmazás.

Kifejezetten olyan munkafolyamatokhoz tervezve, ahol a felhasználó különböző Windows 11 Virtuális Asztalokat dedikál különböző projekteknek. Az alkalmazás képes külön példányokban futni az Asztalokon, és pontosan azt az **emberi munkaidőt** méri, amit ténylegesen az adott Asztalon töltesz.

---

## Fő Jellemzők

1. **Automatikus Windows 11 Virtuális Asztal felismerés:**
   - Indításkor automatikusan kiolvassa a Windows 11 Explorer registryjéből (`HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops`) az adott Asztal nevét (pl. `Kontrolling`, `BA workshop`, `Adománytaxi`) és egyedi GUID azonosítóját.
   - Ha az asztalnak nincs egyedi neve a Windowsban, `Asztal 1`, `Asztal 2` sorszámozást használ.
2. **Asztalváltásra reagálás:**
   - **Elhagyáskor:** Ha átváltasz egy másik Asztalra (miközben itt pl. egy AI ágens vagy háttérfolyamat dolgozik), az aktív időmérést **automatikusan szünetelteti (Pause)** és menti a CSV-be.
   - **Visszatéréskor:** Amikor visszatérsz az Asztalra, a kis widget **automatikusan előtérbe ugrik**, és felajánlja a megkezdett feladat folytatását (*„Folytatod a(z) '...' taskot?”*), de az óra **kizárólag gombnyomásra** indul el.
3. **Asztalonként külön CSV perzisztencia:**
   - Az adatokat különálló fájlokban tárolja a `data/<Asztal_Neve>.csv` útvonalon.
   - **Magyar Excel kompatibilis:** `utf-8-sig` kódolás pontosvessző (`;`) elválasztóval, így dupla kattintással közvetlenül nyitható Excelben az ékezetes karakterek és oszlopok hibátlan megjelenésével.
   - **Zárolási védelem:** Ha a CSV éppen nyitva van Excelben, az alkalmazás nem omlik össze, memóriában tartja a frissítéseket, és jelzi a widgeten a zárolást.
4. **Minimalista lebegő widget + Lenyitható előzmények:**
   - Kompakt widget (~440 × 215 px): nagyméretű, tiszta kontrasztos digitális óra (`Consolas 28 bold`), valós időben szerkeszthető feladatnév mező, Indítás / Szünet / Befejezés / Új gombok, `[📌 Felül / 📍 Normál]` Mindig felül állapotjelző kapcsoló.
   - `[📋 Feladatok]` gombbal lenyitható előzménypanel (~440 × 520 px): korábbi feladatok listája, `[☐ / ☑]` rögzítettnek jelölés (pipálás), nem rögzített és összesített munkaidő kijelzése, valamint `[📂 CSV megnyitása]` közvetlen elérés.

---

## Indítás

### Egyszerű dupla kattintás:
Futtasd a `run.bat` fájlt. Ez a háttérben indítja el a widgetet (`pythonw.exe` segítségével), konzolablak nélkül.

### Parancssori kapcsolók:
```powershell
# Alapértelmezett indítás az aktuális Asztalon
python app.py

# Mindig felül (Always on Top) módban
python app.py --always-on-top

# Egyedi Asztal név felülbírálásával
python app.py --desktop-name "Projekt Alpha"

# Egyedi adatkönyvtár megadásával
python app.py --data-dir "c:\SajatMappa\Adatok"
```

---

## Architektúra és Fájlok

- `app.py`: Belépési pont, CLI paraméterek (`argparse`), hibakezelés.
- `virtual_desktop.py`: Natív Windows 11 Registry olvasó és COM `IVirtualDesktopManager` integráció (`ctypes`).
- `models.py`: `TaskRecord` adatmodell, időtartam formázás (`format_seconds`), státuszok.
- `storage.py`: `CsvTaskRepository`, atomi írás (`.tmp` -> `.csv`), Excel zárolás kezelés.
- `timer_engine.py`: Állapotgép (`TimerSessionController`) driftmentes `time.monotonic()` időméréssel és auto-pause/prompt logikával.
- `ui_widget.py`: Tkinter minimalista lebegő felület és lenyitható történet panel.
- `logger_setup.py`: Rotáló hibaplózás (`error.log`, max 1 MB, 3 mentés, `delay=True`).
- `tests/`: Pytest egységtesztek.

---

## Tesztek Futtatása

```powershell
pytest tests -v
```

