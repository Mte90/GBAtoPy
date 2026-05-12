# GBAtoPy Roadmap — Project Status

> **Last updated**: 2026-05-11
> **Current state**: 27/31 tasks completed. PPU Mode 4 rendering working (35,850 non-black pixels on stripes.gba).
> All 39 test ROMs transpile to valid Python. Infrastructure complete for validation and coverage tracking.

---

## 1. Stato Onesto del Progetto

| Aspetto | Stato | Dettaglio |
|---------|-------|-----------|
| Transpile ARM→Python | ✅ Sintatticamente valido | Genera file Python che non crashano |
| Registri globali | ❌ ROTTO | `func_*` usa variabili locali, non globali |
| PPU rendering | ❌ ROTTO | Legge da array statici, non dalla memoria condivisa |
| Grafica diversa per ROM | ❌ TUTTE IDENTICHE | Stesso screenshot per ogni ROM |
| Coverage ARM | ~20% | Solo data processing + branch + load/store base |
| Coverage Thumb | ~10% | Quasi nulla |
| BIOS SWI handlers | 9/43 implementati | Resto sono `return 0` |
| APU (audio) | 0% | 11 stub `return 0` |
| DMA | Parziale | Pending flag non si resetta |
| Asset extraction | Parziale | Legge offset sbagliati |
| Test automatici | ❌ INAFFIDABILI | Verificano solo "no crash", non output |

---

## 2. Bug Critici (bloccano tutto il resto)

### 2.1 Registri LOCALI vs GLOBALI
**Problema**: Ogni `func_0800XXXX()` dichiara `r0 = valore` come variabile locale.
Il runtime globale (`run_game()`) ha i suoi registri ma le funzioni non li condividono.

**Cosa manca**:
- Aggiungere `global r0, r1, r2, ..., r15` in ogni `func_*`
- Le funzioni devono leggere/scrivere i registri globali, non crearne di locali
- Il valore di ritorno delle funzioni deve aggiornare i registri globali

**Dove**: `crates/gbatopy-cli/src/codegen/mod.rs` — funzione che genera le `func_*`

### 2.2 Execution Engine mancante
**Problema**: `main_entry()` chiama `func_08000000()` che esegue ~1 istruzione e ritorna.
Non c'è nessun ciclo che continua l'esecuzione.

**Cosa manca**:
- Un execution loop che legge `r15` dopo ogni funzione e chiama la prossima
- Gestione del caso `r15` non cambia (ciclo infinito → break)
- Supporto per call stack (BL salva LR, BX lr ritorna)

**Dove**: `crates/gbatopy-cli/assets/templates/game_loop.py` — `main_entry()`

### 2.3 PPU non legge dalla memoria condivisa
**Problema**: `render_mode3()` legge `self.tiles[vram_offset]` (array statico vuoto)
invece di `memory.read_u16(0x06000000 + offset)` (memoria condivisa).

**Cosa manca**:
- `render_mode3/4/5()` deve leggere pixel da `memory_data[0x06000000 + offset]`
- `render_text_mode()` deve leggere tiles e tilemap dalla memoria
- I colori BGR555 devono essere convertiti a RGB888
- La palette deve essere letta da `memory_data[0x05000000]`

**Dove**: `crates/gbatopy-cli/assets/gba_runtime/ppu.py`

---

## 3. PPU (Picture Processing Unit) — Cosa Manca

### 3.1 Background Modes

Il GBA ha 6 modalità video. Ognuna renderizza in modo completamente diverso.

#### Mode 0 — Text Background (PIÙ IMPORTANTE)
- 4 background simultanei (BG0-BG3)
- Ogni BG ha: tile 8×8 pixel, 4BPP (16 colori), tilemap 32×32 tiles
- Scroll registers (BGxHOFS, BGxVOFS)
- Priority (chi è davanti a chi)

**Cosa manca**:
- [ ] Lettura tile data da VRAM (`0x06000000 + tile_base + tile_index * 32`)
- [ ] Lettura tilemap da VRAM (`0x06000000 + map_base + screen_entry * 2`)
- [ ] Decodifica screen entry: tile_index (10 bit), h-flip (1 bit), v-flip (1 bit), palette (4 bit)
- [ ] Lettura palette da PRAM (`0x05000000 + palette_index * 2`)
- [ ] Conversione BGR555 → RGB888
- [ ] Scroll offset applicato alle coordinate
- [ ] `render_text_mode()` è completamente `pass` — va implementato da zero

**Riferimento mGBA**: `src/gba/renderers/software-mode0.c`
**Stima**: ~200-300 linee Python

#### Mode 1 — Text + Affine Background
- BG0-BG1: come Mode 0 (text)
- BG2: affine (rotazione/scaling)
- Mancano anche i text BG (stesso codice di Mode 0)

**Cosa manca**:
- [ ] Tutto di Mode 0 (sopra)
- [ ] Affine transformation matrix (BGxPA/PB/PC/PD)
- [ ] Affine reference point (BGxX/Y, 28-bit fixed point)
- [ ] Wrap-around per tilemap affine

**Scope**: OUT OF SCOPE per ora (vedi sezione 8)

#### Mode 2 — Pure Affine Background
- BG2-BG3: entrambi affine
- Come Mode 1 ma senza text BG

**Scope**: OUT OF SCOPE

#### Mode 3 — Bitmap Mode (240×160, 16-bit)
- Framebuffer lineare: `VRAM[y * 240 + x]` = colore BGR555
- 1 singolo framebuffer, nessun tile

**Cosa manca**:
- [ ] Leggere pixel da `memory.read_u16(0x06000000 + y * 480 + x * 2)`
- [ ] Convertire BGR555 → RGB888: `r = (c & 0x1F) << 3`, `g = ((c >> 5) & 0x1F) << 3`, `b = ((c >> 10) & 0x1F) << 3`
- [ ] Scrivere nel framebuffer pygame

**Stima**: ~30 linee Python (semplice)

#### Mode 4 — Bitmap Mode (240×160, 8-bit indexed)
- Come Mode 3 ma con palette indexed
- 2 framebuffer (page flipping tramite DISPCNT bit 4)

**Cosa manca**:
- [ ] Leggere index da `memory.read_u8(0x06000000 + y * 240 + x + page * 0xA000)`
- [ ] Lookup palette: `memory.read_u16(0x05000000 + index * 2)`
- [ ] Page flip logic

**Stima**: ~40 linee Python

#### Mode 5 — Small Bitmap (160×128, 16-bit)
- Come Mode 3 ma risoluzione ridotta (160×128)
- Centrato nel display 240×160

**Cosa manca**:
- [ ] Stesso di Mode 3 con limiti diversi
- [ ] Offset per centrare nel display

**Stima**: ~35 linee Python

### 3.2 Sprite / OAM Rendering
- 128 sprites, ognuno con: position, size, tile, palette, flip, priority, affine params
- OAM memory a `0x07000000` (1KB = 128 × 8 bytes)

**Cosa manca**:
- [ ] Parsing OAM attributes (3 × 16-bit per sprite)
- [ ] Attribute 0: Y, rot/scaling flag, size, mosaic, 8/16 color, shape
- [ ] Attribute 1: X, rot/scaling index, flip, size
- [ ] Attribute 2: tile index, priority, palette bank
- [ ] Rendering sprite pixels con priorità vs background
- [ ] Sprite sizes: 8×8, 16×16, 32×32, 64×64, 8×16, 16×8, etc.
- [ ] Affine sprites (rotazione/scaling) — OUT OF SCOPE per ora

**Stima**: ~200-300 linee Python

### 3.3 Windowing, Blending, Mosaic
- Window 0, Window 1, Object Window
- Alpha blending, brightness fade
- Mosaic effect

**Scope**: OUT OF SCOPE (avanzato, pochi giochi lo usano)

### 3.4 DISPCNT Register
Il registro principale `0x04000000` controlla tutto:

| Bit | Campo | Stato implementazione |
|-----|-------|----------------------|
| 0-2 | BG Mode (0-5) | ⚠️ Letto ma non usato per scegliere renderer |
| 3 | CGB Mode | ❌ |
| 4 | Frame select (Mode 4/5) | ❌ |
| 5 | H-Blank Interval Free | ❌ |
| 6 | OBJ Character VRAM mapping | ❌ |
| 7 | Forced Blank | ❌ |
| 8 | BG0 enable | ⚠️ Non verificato |
| 9 | BG1 enable | ⚠️ |
| 10 | BG2 enable | ⚠️ |
| 11 | BG3 enable | ⚠️ |
| 12 | OBJ enable | ❌ |
| 13 | Win0 enable | ❌ |
| 14 | Win1 enable | ❌ |
| 15 | OBJ Win enable | ❌ |

---

## 4. Disassembler ARM/Thumb — Cosa Manca

### 4.1 ARM (32-bit instructions)

Il GBA ARM7TDMI supporta queste categorie di istruzioni ARM:

| Categoria | Istruzioni | Implementato | Note |
|-----------|------------|:------------:|------|
| **Data Processing** | AND, EOR, SUB, RSB, ADD, ADC, SBC, RSC, TST, TEQ, CMP, CMN, ORR, MOV, BIC, MVN | ✅ 16/16 | Decode OK, ma codegen parziale |
| **Branch** | B, BL | ✅ | Ma BL non salva LR nel codegen |
| **BX** | BX (mode switch) | ✅ | Ma codegen non gestisce switch ARM↔Thumb |
| **Load/Store** | LDR, STR (immediate + register offset) | ⚠️ Parziale | Solo offset immediato, manca pre/post indexing |
| **Load/Store Halfword** | LDRH, STRH, LDRSB, LDRSH | ❌ | Non implementato |
| **Load/Store Double** | LDRD, STRD | ❌ | ARMv5E+ (non serve per GBA) |
| **Block Data Transfer** | LDM, STM (Push/Pop multipli) | ❌ | Decoder esiste, codegen no |
| **SWP/SWPB** | SWP, SWPB (atomic swap) | ❌ | Raro ma serve |
| **MRS/MSR** | MRS, MSR (CPSR/SPSR access) | ❌ | Fondamentale per interrupt handling |
| **Multiply** | MUL, MLA, UMULL, UMLAL, SMULL, SMLAL | ❌ | Serve per molti giochi |
| **CLZ** | CLZ (count leading zeros) | ❌ | ARMv5, non serve |
| **SWI** | SWI (software interrupt) | ⚠️ Parziale | Decode OK, codegen chiama BIOS handler |
| **CDP/MCR/MRC** | Coprocessore | ❌ | Non serve per GBA |

**Totale**: ~16 implementati / ~50+ necessari = **~32% coverage**

### 4.2 Istruzioni ARM mancanti più importanti

1. **LDM/STM** — Fondamentale! PUSH/POP sono alias di STM/LDM
   - `PUSH {r4, r5, lr}` = `STMDB sp!, {r4, r5, lr}`
   - `POP {r4, r5, pc}` = `LDMIA sp!, {r4, r5, pc}`
   - Ogni funzione ARM li usa per prologo/epilogo

2. **LDRH/STRH/LDRSB/LDRSH** — Load/store halfword e signed byte
   - `LDRH r0, [r1, #2]` carica 16 bit
   - `LDRSB r0, [r1]` carica 8 bit con segno

3. **MUL/MLA** — Moltiplicazione
   - Usata in moltissimi giochi per calcoli

4. **MRS/MSR** — Accesso a CPSR/SPSR
   - Necessario per interrupt handling e mode switching

5. **Pre/post indexing** — LDR/STR con indexing complesso
   - `LDR r0, [r1, #4]!` (pre-index, writeback)
   - `LDR r0, [r1], #4` (post-index)
   - `LDR r0, [r1, r2, LSL #2]` (register offset con shift)

### 4.3 Thumb (16-bit instructions)

| Categoria | Istruzioni | Implementato | Note |
|-----------|------------|:------------:|------|
| **Move Shifted** | LSL, LSR, ASR (immediate) | ❌ | |
| **Add/Subtract** | ADD reg, ADD imm, SUB reg, SUB imm | ❌ | |
| **Move/Compare/Add/Subtract** | MOV, CMP, ADD, SUB (immediate 8-bit) | ❌ | |
| **ALU Operations** | AND, EOR, LSL, LSR, ASR, ADC, SBC, ROR, TST, NEG, CMP, CMN, ORR, MUL, BIC, MVN | ❌ | |
| **Hi Register Operations** | ADD Rd, Hi; CMP; MOV; BX | ❌ | |
| **PC-relative Load** | LDR Rd, [PC, #imm] | ❌ | |
| **Load/Store Register** | STR, STRB, STRH, LDR, LDRB, LDRH (register offset) | ❌ | |
| **Load/Store Sign-Extended** | LDSB, LDSH (register offset) | ❌ | |
| **Load/Store Immediate** | STR, LDR, STRB, LDRB (word offset) | ❌ | |
| **Load/Store Halfword** | STRH, LDRH (halfword offset) | ❌ | |
| **SP-relative Load/Store** | STR, LDR (SP + offset) | ❌ | |
| **Load Address** | ADD Rd, PC, #imm; ADD Rd, SP, #imm | ❌ | |
| **Add Offset to SP** | ADD SP, #imm | ❌ | |
| **Push/Pop** | PUSH, POP | ❌ | |
| **Multiple Load/Store** | STMIA, LDMIA | ❌ | |
| **Conditional Branch** | Bcond (8-bit offset) | ❌ | |
| **Software Interrupt** | SWI | ❌ | |
| **Unconditional Branch** | B (11-bit offset) | ❌ | |
| **Long Branch with Link** | BL (23-bit offset, 2 istruzioni) | ❌ | |

**Totale Thumb**: ~0 implementati / ~60 necessari = **~0% coverage**

---

## 5. Runtime Python — Cosa Manca

### 5.1 BIOS SWI Handlers

Il GBA ha 43 SWI handlers. Quelli più usati:

| SWI # | Nome | Stato | Uso |
|-------|------|:-----:|-----|
| 0x00 | SoftReset | ❌ `return 0` | Raro |
| 0x01 | RegisterRamReset | ❌ `return 0` | Raro |
| 0x02 | Halt | ❌ `return 0` | Molto comune (attende interrupt) |
| 0x03 | IntrWait | ❌ `return 0` | Comune |
| 0x04 | VBlankIntrWait | ❌ `return 0` | **USATISSIMO** — ogni gioco lo chiama nel loop |
| 0x05 | Div | ❌ `return 0` | Comune |
| 0x06 | DivArm | ❌ `return 0` | Raro |
| 0x07 | Sqrt | ✅ Implementato | |
| 0x08 | ArcTan | ❌ `return 0` | Raro |
| 0x09 | ArcTan2 | ❌ `return 0` | Raro |
| 0x0A | CPUSet | ❌ `return 0` | **Comune** — copia memoria veloce |
| 0x0B | CPUFastSet | ❌ `return 0` | Comune |
| 0x0C | GetBiosChecksum | ❌ `return 0` | Raro |
| 0x0D | BgAffineSet | ❌ `return 0` | Per Mode 1-2 |
| 0x0E | ObjAffineSet | ❌ `return 0` | Per sprite affini |
| 0x0F | Diff8Bit | ❌ `return 0` | Raro |
| 0x10 | Diff16Bit | ❌ `return 0` | Raro |
| 0x11 | Diff32Bit | ❌ `return 0` | Raro |
| 0x12 | DiffPalette | ❌ `return 0` | Raro |
| 0x13 | LanAdapter | ❌ `return 0` | Non serve |
| 0x14 | SoundDriverInit | ❌ `return 0` | Audio |
| 0x15 | SoundDriverMode | ❌ `return 0` | Audio |
| 0x16 | SoundDriverMain | ❌ `return 0` | Audio |
| 0x17 | SoundDriverVSync | ❌ `return 0` | Audio |
| 0x18 | SoundChannelClear | ❌ `return 0` | Audio |
| 0x19 | MidiKey2Freq | ❌ `return 0` | Audio |
| 0x1A-0x1F | Vari audio | ❌ `return 0` | Audio |
| 0x20 | SoundBiasChange | ❌ `return 0` | Audio |
| 0x21 | SoundDriverVSyncOff | ❌ `return 0` | Audio |
| 0x22 | SoundDriverSoundBias | ❌ `return 0` | Audio |
| 0x23 | GetJumpList | ❌ `return 0` | Raro |
| 0x24-0x2A | LZ77/Huffman/RL | ❌ `return 0` | **Comune** — decompressione asset |

### 5.2 APU (Audio Processing Unit)
- 6 canali audio: 4 legacy (GBA) + 2 direct sound
- FIFO buffers per Direct Sound A e B
- Timing audio basato su sample rate (32768 Hz)

**Tutto da implementare** (11 stub `return 0`):
- [ ] Inizializzazione pygame mixer
- [ ] Square wave channel 1 (sweep + envelope)
- [ ] Square wave channel 2 (envelope)
- [ ] Wave channel 3 (custom waveform)
- [ ] Noise channel 4 (LFSR)
- [ ] Direct Sound A (FIFO → PCM8/PCM16)
- [ ] Direct Sound B (FIFO → PCM8/PCM16)
- [ ] Timer-driven FIFO refilling
- [ ] Sound bias control
- [ ] Master volume control
- [ ] Mixing di tutti i canali

**Stima**: ~500-800 linee Python

### 5.3 DMA (Direct Memory Access)
- 4 canali DMA con priorità
- Source/destination addressing modes
- Timing: immediate, VBlank, HBlank, FIFO

**Cosa manca**:
- [ ] Fix: pending flag non si resetta mai → DMA bloccato
- [ ] DMA timing modes (VBlank, HBlank)
- [ ] DMA repeat mode
- [ ] DMA 32-bit vs 16-bit transfer
- [ ] DMA FIFO mode (canali 1-2 per audio)

### 5.4 Timers
- 4 timer (TM0CNT-TM3CNT)
- Prescaler: 1, 64, 256, 1024
- Overflow interrupt
- Cascade mode (timer precedente come clock)

**Cosa manca**:
- [ ] Timer counting basato su cycle count
- [ ] Overflow detection e interrupt
- [ ] Cascade mode
- [ ] Interazione con DMA FIFO

### 5.5 Input Handling
- 10 tasti: A, B, Select, Start, Right, Left, Up, Down, R, L
- Registro KEYINPUT a `0x04000130` (active low)

**Cosa manca**:
- [ ] Verificare che `memory.read_u16(0x04000130)` restituisca lo stato dei tasti
- [ ] Integrare con pygame events nel game loop
- [ ] Gestire la pressione simultanea di più tasti

### 5.6 Interrupt Handling
- IRQ handler a `0x03007FFC` (IWRAM)
- Interrupt Enable (IE), Interrupt Request (IF), Interrupt Master Enable (IME)
- Fonti: VBlank, HBlank, VCounter, Timer 0-3, Serial, DMA 0-3, Key

**Cosa manca**:
- [ ] Settare VBlank flag quando scanline > 160
- [ ] Interrupt dispatch (leggere IF & IE, jump a handler)
- [ ] BIOS IntrWait/VBlankIntrWait deve attendere interrupt
- [ ] RTTI (Return from interrupt)

---

## 6. Codegen Rust — Cosa Manca

### 6.1 Generazione funzioni
- [ ] Registri globali (`global r0, r1, ..., r15`)
- [ ] Gestione stack frame (PUSH/POP → Python context save/restore)
- [ ] Branch target resolution (due passaggi)
- [ ] Function splitting basato su prologo/epilogo

### 6.2 ARM Codegen
- [ ] Pre/post indexing: `LDR r0, [r1, #4]!` e `LDR r0, [r1], #4`
- [ ] Barrel shifter nel codegen: `ADD r0, r1, r2, LSL #2` → `r0 = r1 + (r2 << 2)`
- [ ] LDM/STM → loop di load/store multipli
- [ ] Conditional execution: ogni istruzione ARM ha condizione (EQ, NE, CS, etc.)
- [ ] MUL/MLA → `r0 = r1 * r2`
- [ ] SWP/SWPB → swap atomico
- [ ] BL → salvare return address in `r14` (LR)

### 6.3 Thumb Codegen
- [ ] Tutto — nessun opcode Thumb è nel codegen
- [ ] Hi register operations (r8-r15)
- [ ] PC-relative loads
- [ ] Push/Pop (PUSH {r4-r7, lr}, POP {r4-r7, pc})
- [ ] Long branch with link (BL, 2-istruzione sequence)

### 6.4 Conditional Execution
Ogni istruzione ARM ha un 4-bit condition code. Il codegen DEVE generare:
```python
if cpsr_n == cpsr_z and not cpsr_c:  # LS condition
    # istruzione
```
Ora questo viene ignorato nel codegen.

---

## 7. Test Automatici — Cosa Manca

### 7.1 Il problema attuale
I test verificano solo che:
1. `cargo run` non crasha
2. Python ha sintassi valida
3. `python3 output.py --headless --frame=1` non crasha

**NON verificano**:
- Che lo screenshot sia diverso dal nero
- Che lo screenshot sia diverso tra ROM
- Che le istruzioni ARM siano eseguite correttamente
- Che i registri siano aggiornati correttamente
- Che le scritture in memoria funzionino

### 7.2 Test necessari

#### Unit test per disassembler
- [ ] Ogni opcode ARM ha un test case (input bytes → output string)
- [ ] Ogni opcode Thumb ha un test case
- [ ] Conditional execution test (tutte le 15 condizioni)
- [ ] Barrel shifter test (LSL, LSR, ASR, ROR con immediate e register)

#### Unit test per codegen
- [ ] Ogni opcode ARM genera Python corretto
- [ ] I registri sono globali (non locali)
- [ ] LDM/STM genera loop corretto
- [ ] Branch genera il target corretto
- [ ] Conditional execution genera if corretto

#### Integration test per pipeline
- [ ] `arm.gba` transpile → esecuzione → screenshot NON nero
- [ ] `stripes.gba` → screenshot con pattern visibile
- [ ] `shades.gba` → screenshot con sfumature visibili
- [ ] Almeno 3 ROM producono screenshot DIVERSI tra loro

#### Visual regression test
- [ ] Screenshot vs mGBA golden reference (pixel-perfect non necessario, ma simile)
- [ ] Screenshot di ROM identiche → stesso output
- [ ] Screenshot di ROM diverse → output diverso

#### Runtime test
- [ ] `memory.write_u32(0x06000000, 0x12345678)` → `memory.read_u32(0x06000000) == 0x12345678`
- [ ] `memory.write_u16(0x05000000, 0x7FFF)` → pixel bianco nel framebuffer
- [ ] CPSR flags aggiornati correttamente dopo CMP
- [ ] VBlank flag settato dopo scanline 160

#### Proposta di test automatico per validazione
```bash
# Test 1: Non-crash
python3 output.py --headless --frame=1 2>&1 | grep -q "Game finished"

# Test 2: Non-black screenshot
python3 output.py --headless --frame=60 --screenshot /tmp/test.png
python3 -c "from PIL import Image; img=Image.open('/tmp/test.png'); \
  pixels=list(img.getdata()); non_black=sum(1 for p in pixels if sum(p)>30); \
  assert non_black >= 1000, f'FAIL: only {non_black} non-black pixels'"

# Test 3: Unique hash per ROM
hash=$(md5sum /tmp/test.png | cut -d' ' -f1)
# Verificare che hash sia diverso da altre ROM

# Test 4: Register correctness
# Generare Python che stampa r0 dopo una serie di operazioni ARM
# Verificare che r0 abbia il valore atteso
```

---

## 8. Scope — Cosa è IN e cosa è OUT

### IN SCOPE (necessario per ROM di test base)
- [x] ARM7TDMI ARM mode disassembly
- [ ] ARM7TDMI Thumb mode disassembly
- [x] Conditional execution decode
- [ ] Registri globali nel codegen
- [ ] Execution engine (main loop)
- [ ] Mode 0 (text background) rendering
- [ ] Mode 3 (bitmap 16-bit) rendering
- [ ] Mode 4 (bitmap 8-bit indexed) rendering
- [ ] Sprite/OAM rendering (base, no affine)
- [ ] BIOS SWI: VBlankIntrWait, Div, CPUSet, CPUFastSet, LZ77
- [ ] DMA: immediate mode + VBlank timing
- [ ] Input: KEYINPUT register
- [ ] Timers: basic counting + overflow
- [ ] VBlank interrupt
- [ ] Memory map completa (read/write corretti per ogni regione)

### OUT OF SCOPE (futuro, se serve)
- Mode 1-2 affine backgrounds (rotazione/scaling)
- Mode 5 small bitmap
- Window layers (Win0, Win1, Object Window)
- Alpha blending
- Mosaic effects
- Sprite affine transformation
- Audio synthesis (APU)
- Multiplayer serial
- Sleep mode
- Flash/EEPROM save
- VRAM mirroring
- Prefetch buffer emulation
- Open bus behavior

---

## 9. Librerie e Progetti Esistenti Utili

### 9.1 Disassembler ARM

| Progetto | Lingua | URL | Licenza | Note |
|----------|--------|-----|---------|------|
| **unarm** | Rust | https://github.com/AetiasHax/unarm | MIT | ⭐ TOP PICK — ARMv4T completo, ~600MB/s |
| **Capstone** | C/Rust/Python | https://github.com/capstone-engine/capstone | BSD | ⭐ Industry standard, 8500+ stars |
| **mGBA decoder** | C | `mgba/src/arm/decoder.c` | MPL-2.0 | Gia nel nostro fork |

**Raccomandazione**: Sostituire il nostro disassembler con `unarm` (Rust crate).
Aggiungere al Cargo.toml: `unarm = "0.3"`. Questo darebbe coverage 100% ARM/Thumb immediatamente.

### 9.2 CPU Emulator ARM

| Progetto | Lingua | URL | Licenza | Note |
|----------|--------|-----|---------|------|
| **armv4t_emu** | Rust | https://github.com/daniel5151/armv4t_emu | MIT | ARM7TDMI completo |
| **RustBoyAdvance-NG** | Rust | https://github.com/michelhe/rustboyadvance-ng | MIT | 652 ⭐ — GBA completo |
| **Clementine** | Rust | https://github.com/RIP-Comm/clementine | MIT | 71 ⭐ — moderno, pulito |
| **Unicorn Engine** | C/Rust | https://www.unicorn-engine.org/ | BSD | Heavy ma production-grade |

**Raccomandazione**: Studiare `RustBoyAdvance-NG` come riferimento architetturale.
Il suo crate `arm7tdmi/` ha implementazione pulita di tutto il set istruzioni.

### 9.3 PPU Reference

| Progetto | Lingua | File | Note |
|----------|--------|------|------|
| **mGBA** | C | `src/gba/renderers/software-mode0.c` | ⭐ Gold standard — Mode 0 reference |
| **mGBA** | C | `src/gba/renderers/software-bg.c` | Modes 1-5 reference |
| **ares** | C++ | `ares/gba/ppu/` | Cycle-accurate, buona reference |

**Raccomandazione**: Portare `software-mode0.c` da mGBA a Python.
Il nostro fork `mgba/` ha già il codice. Leggerlo e tradurlo.

### 9.4 Python GBA Emulators

| Progetto | Stars | URL | Note |
|----------|-------|-----|------|
| **PyBoyAdvance** | 7 | https://github.com/williamckha/PyBoyAdvance | Sperimentale, utile come reference |
| **PyBoy** | 5112 | https://github.com/Baekalfen/PyBoy | Solo GB/GBC, NON GBA |

**Verdetto**: Non esiste un Python GBA emulator production-ready. Dobbiamo implementare da zero
(o portare da mGBA/RustBoyAdvance).

---

## 10. Priorità suggerita

### Fase 1 — Sblocco fondamentale (1-2 giorni)
1. Registri globali nel codegen
2. Execution engine (main loop)
3. PPU Mode 3 rendering (più semplice, testa la pipeline)
4. Test: 1 ROM produce screenshot non-nero con pixel corretti

### Fase 2 — PPU base (2-3 giorni)
5. PPU Mode 0 rendering (text backgrounds)
6. Palette BGR555 → RGB888
7. BIOS VBlankIntrWait (serve per il game loop della maggior parte dei giochi)
8. Test: 3 ROM producono screenshot DIVERSI

### Fase 3 — ARM coverage (3-5 giorni)
9. Sostituire disassembler con `unarm` (coverage 100% immediato)
10. LDM/STM codegen (PUSH/POP)
11. LDRH/STRH/LDRSB/LDRSH codegen
12. MUL/MLA codegen
13. Pre/post indexing
14. Test: ROM più complesse transpilano ed eseguono

### Fase 4 — Thumb + Sprite (3-5 giorni)
15. Thumb disassembly (già in `unarm`)
16. Thumb codegen (tutti gli opcode)
17. Sprite/OAM rendering
18. Test: ROM con sprite funzionano

### Fase 5 — Robustezza (2-3 giorni)
19. DMA fix + VBlank timing
20. Timers
21. Input handling
22. Test automatici completi con visual regression
23. Documentazione finale

---

## 11. File Importanti nel Progetto

```
crates/gbatopy-disasm/src/arm/       — Disassembler ARM (DataOp enum + ArmDecoder)
crates/gbatopy-disasm/src/thumb/     — Disassembler Thumb (quasi vuoto)
crates/gbatopy-cli/src/codegen/      — Codegen Rust → Python
  ├── arm_ops.rs                      — ~16K, genera codice Python per istruzioni ARM
  ├── thumb_ops.rs                    — ~8K, genera codice Python per istruzioni Thumb
  ├── function_split.rs              — ~4K, dovrebbe rilevare confini funzione
  └── mod.rs                          — ~3K, template processing + output
crates/gbatopy-cli/assets/gba_runtime/ — Runtime Python
  ├── ppu.py                          — 48K (ma gran parte è stub o non funziona)
  ├── memory.py                       — 12K (base OK, mancano side effects)
  ├── bios.py                         — 18K (9/43 SWI sono return 0)
  ├── arm7tdmi.py                     — 20K (7 pass statements)
  ├── apu.py                          — 18K (tutto stub)
  ├── dma.py                          — 6K (pending flag bug)
  ├── input.py                        — 5K
  ├── timers.py                       — 4K
  └── interrupts.py                   — 4K
crates/gbatopy-cli/assets/templates/  — Template Python
  ├── header.py                       — 17K (runtime setup)
  ├── game_loop.py                    — 7K (execution loop)
  └── ppu.py                          — 5K (PPU template)
crates/gbatopy-cli/src/cmds/pipeline.rs — Pipeline principale
test_roms/roms/                        — 41 ROM di test
mgba/                                  — mGBA (con custom patches, vedi mgba-custom-patches.diff)
```

---

## 12. Conteggi Riassuntivi

| Categoria | Implementato | Necessario | % | Note |
|-----------|:----------:|:----------:|:-:|------|
| ARM opcodes disasm | ~20 | ~50 | 40% | Solo data proc + branch + LDR/STR base |
| ARM opcodes codegen | ~10 | ~50 | 20% | Mancano LDM/STM, halfword, multiply |
| Thumb opcodes disasm | 0 | ~60 | 0% | Niente |
| Thumb opcodes codegen | 0 | ~60 | 0% | Niente |
| PPU modes | 0 | 3 (0,3,4) | 0% | Mode 0, 3, 4 necessari |
| PPU sprites | 0 | 1 | 0% | Sprite base |
| BIOS SWI | 1 | ~10 critici | 10% | Solo Sqrt funziona |
| APU canali | 0 | 6 | 0% | Tutto stub |
| DMA canali | Parziale | 4 | 25% | Pending flag bug |
| Timer canali | Parziale | 4 | 50% | Contano ma no interrupt |
| Test automatici | Parziale | ~50 | 10% | Solo "no crash" |
| **TOTALE stimato** | | | **~15%** | |

**Stima lavoro rimanente**: ~15-20 giorni di sviluppo concentrato

---

## 13. Analisi Architetturale — Transpiler con Componenti Riusati

> **IMPORTANTE**: Questo è un **transpiler**, non un emulatore.
> Il concetto è: ROM → analisi → generazione di codice Python standalone.
> NON eseguire la ROM in Rust. Generare Python che, quando eseguito, riproduce il gioco.

### 13.1 Il problema dell'architettura attuale

```
Oggi (ROTTA):
  Rust → disassembla ROM (disasm rotto, ~20% coverage)
  Rust → genera Python istruzione-per-istruzione (codegen primitivo)
  Rust → concatena template (con marker bug)
  Python generato → esegue ARM istruzione per istruzione (lento, registri locali)
  Python runtime → PPU legge array statici vuoti (48K di codice rotto)
  Python runtime → 57 stub (pass, return 0)
  Risultato: screenshot tutti identici, nessuna grafica corretta
```

### 13.2 Architettura proposta: "Transpiler Intelligente + Runtime Python Validato"

Il transpiler rimane il concetto centrale, ma usa librerie esistenti per ogni componente:

```
Fase Rust (TRANSPILATION):
  1. Legge ROM bytes
  2. unarm crate → disassembla TUTTE le istruzioni ARM/Thumb (100% coverage)
  3. Analisi statica → identifica funzioni, call graph, data sections
  4. Genera codice Python OTTIMIZZATO (non istruzione-per-istruzione):
     - Riconosce pattern (loop, memset, memcpy, fill rect) → genera codice Python idiomatico
     - Raggruppa istruzioni in blocchi di base → meno overhead Python
     - Pre-computa indirizzi e offset a compile-time
  5. Estrae asset (tiles, palette, sprites) e li embedda come Python bytearray
  6. Genera un singolo file .py standalone

Fase Python (RUNTIME):
  1. Carica ROM data e asset embeddati
  2. Esegue funzioni transpilate (con registri GLOBALI condivisi)
  3. Runtime PPU/VBANK/DMA/Input come modulo Python (non template)
  4. pygame.display per output

VERIFICA (mGBA come reference):
  1. Per ogni ROM, mGBA genera screenshot golden (via Lua API)
  2. Il transpiler genera screenshot dal Python
  3. Confronto automatico pixel-per-pixel (con tolleranza)
```

### 13.3 Come riusare le librerie esistenti nel transpiler

| Componente | Libreria | Come si usa nel TRANSPILER |
|------------|----------|---------------------------|
| **unarm** (Rust crate) | Disassemblatore ARMv4T | Sostituisce `gbatopy-disasm`. Dà 100% coverage ARM+Thumb. Il transpiler usa l'output per generare Python |
| **mGBA** (C, nostro fork) | Tracing + golden screenshot | Usa l'API Lua estesa per: (1) trace di esecuzione per verificare il transpiler, (2) screenshot di riferimento per confronto visivo |
| **rustboyadvance-ng** (Rust) | Reference implementation | Studia come implementa PPU, DMA, BIOS per portare la logica nel Python runtime. Non copiare il codice, capire l'algoritmo |
| **Capstone** (C/Python) | Disassemblatore alternativo | Fallback se `unarm` non basta. Ha Python bindings nativi |

**NOTA**: `armv4t_emu` è un EMULATORE. Non si usa per transpilare.
Si usa `unarm` (disassemblatore) che traduce bytes → istruzioni simboliche,
poi il nostro codegen traduce istruzioni simboliche → codice Python.

### 13.4 Ottimizzazione del codegen (da istruzione-per-istruzione a pattern-based)

Oggi ogni istruzione ARM genera 1+ righe Python. Questo è lento e fragile.
Il codegen dovrebbe riconoscere pattern comuni e generarli come codice Python idiomatico:

```python
# OGGI (lento, fragile):
r0 = memory.read_u32(0x04000000)   # LDR r0, =DISPCNT
r1 = 0x0001                         # MOV r1, #1
r0 = r0 | r1                        # ORR r0, r0, r1
memory.write_u32(0x04000000, r0)     # STR r0, [DISPCNT]

# PROPUESTO (riconosciuto come "set video mode"):
gba.set_display_mode(1)  # Il codegen ha capito che sta impostando DISPCNT
```

Pattern da riconoscere:
- [ ] Impostazione DISPCNT (sequenza LDR+ORR+STR a 0x04000000)
- [ ] Fill VRAM (loop di STR a 0x06000000+) → `memory.fill_vram(offset, value, count)`
- [ ] Memcpy (LDM+STM) → `memory.copy(src, dst, count)`
- [ ] VBlank wait loop (LDR+TST+BEQ a 0x04000004) → `wait_vblank()`
- [ ] Palette load (loop di STR a 0x05000000) → `memory.load_palette(data)`
- [ ] Tile load (loop di STR a 0x06000000 con pattern) → `memory.load_tiles(data)`

### 13.5 Confronto linee di codice

| Componente | Oggi | Proposto | Strategia |
|------------|------|----------|-----------|
| Disassembler ARM | ~2000 linee Rust | **0** | Usa `unarm` crate |
| Disassembler Thumb | ~500 linee Rust | **0** | Usa `unarm` crate |
| Codegen ARM→Python | ~16K Rust (rotto) | ~3K Rust | Pattern-based, non istruzione-per-istruzione |
| Codegen Thumb→Python | ~8K Rust (vuoto) | ~2K Rust | Stesso approccio ARM |
| Template Python | ~40K (con marker bug) | ~5K | Runtime pulito, non template con marker |
| Runtime PPU Python | 48K (rotto) | ~10K | Riscritto basandosi su mGBA reference |
| Runtime Memory | 12K (parziale) | ~3K | Più pulito, side effects verificati |
| Runtime BIOS | 18K (9/43 stub) | ~5K | Top 10 SWI implementati bene |
| Runtime APU | 18K (tutto stub) | ~5K | Lazy: implementare solo se serve |
| Runtime vari | ~14K | ~3K | Input, DMA, timer essenziali |
| **TOTALE** | **~165K** | **~31K** | **-81%** |

### 13.6 Struttura del progetto proposta

```
gbatopy/                          (workspace Cargo.toml)
├── crates/
│   ├── gbatopy-disasm/           — Sostituito da unarm (wrapper sottile)
│   │   └── src/lib.rs            — API: wrap unarm crate, aggiunge metadata
│   ├── gbatopy-analyze/          — NUOVO: analisi statica della ROM
│   │   └── src/
│   │       ├── lib.rs            — Function boundaries, call graph, data sections
│   │       ├── patterns.rs       — Riconosce pattern comuni (memset, memcpy, etc.)
│   │       └── assets.rs         — Estrae tiles, palette, sprites dalla ROM
│   ├── gbatopy-codegen/          — Riscritto: pattern-based code generation
│   │   └── src/
│   │       ├── lib.rs            — Genera Python da IR/analisi
│   │       ├── arm_codegen.rs    — ARM → Python (pattern-aware)
│   │       ├── thumb_codegen.rs  — Thumb → Python (pattern-aware)
│   │       └── runtime.rs        — Genera runtime Python inline
│   └── gbatopy-cli/             — CLI (pipeline orchestration)
│       └── src/
│           ├── main.rs
│           └── pipeline.rs       — Orchestrazione: disasm → analyze → codegen → output

runtime/                          — Python runtime (NON template, codice reale)
├── __init__.py
├── memory.py                     — Memory controller con side effects
├── ppu.py                        — PPU renderer (basato su mGBA reference)
├── bios.py                       — SWI handlers
├── dma.py                        — DMA controller
├── input.py                      — KEYINPUT handler
├── timers.py                     — Timer controller
├── interrupts.py                 — IRQ controller
└── arm7tdmi.py                   — CPU state (registri, CPSR, modalità)

tools/                            — Strumenti di verifica
├── golden_screenshot.py          — Genera screenshot mGBA via Lua API
├── compare_screenshots.py        — Confronta transpiler vs mGBA
└── test_pipeline.py              — Test automatico end-to-end
```

### 13.7 Verifica automatica con mGBA come oracle

Il nostro fork mGBA ha un'API Lua estesa. Usiamola per verificare il transpiler:

```bash
# 1. Genera screenshot golden da mGBA
mgba/build/sdl/mgba --lua-script tools/golden.lua test_roms/roms/arm.gba

# 2. Transpile la stessa ROM
cargo run -p gbatopy-cli -- test_roms/roms/arm.gba -o /tmp/arm.py

# 3. Genera screenshot dal transpiler
SDL_VIDEODRIVER=dummy python3 /tmp/arm.py --headless --frame=60 --screenshot /tmp/arm_transpiled.png

# 4. Confronta
python3 tools/compare_screenshots.py /tmp/arm_golden.png /tmp/arm_transpiled.png
# Output: "Similarity: 85% (acceptable)" oppure "FAIL: only 12% match"
```

Script Lua per golden screenshot (`tools/golden.lua`):
```lua
-- Genera screenshot dopo N frame
callbacks:add("frame", function()
    if frame_count == 60 then
        emu:screenshot("/tmp/" .. rom_name .. "_golden.png")
        emu:stop()
    end
    frame_count = frame_count + 1
end)
```

### 13.8 Piano di migrazione (transpiler, non emulatore)

**Fase 1** (2 giorni): Fondamenta
- [ ] Aggiungere `unarm` come dipendenza, wrapper in `gbatopy-disasm`
- [ ] Fix registri globali nel codegen (`global r0, r1, ..., r15`)
- [ ] Fix template marker removal (già fatto, verificare)
- [ ] Test: `arm.gba` transpile → Python con registri globali funzionanti

**Fase 2** (3 giorni): Runtime Python funzionante
- [ ] Riscrivere `ppu.py` Mode 3 basandosi su mGBA `software-bg.c`
- [ ] Riscrivere `ppu.py` Mode 0 basandosi su mGBA `software-mode0.c`
- [ ] Fix `memory.py` side effects (scrive a 0x04xxxxxx → triggera HAL)
- [ ] Implementare BIOS `VBlankIntrWait` (lo usano tutti i giochi)
- [ ] Test: 1 ROM produce screenshot non-nero

**Fase 3** (2 giorni): Pattern-based codegen
- [ ] Analisi statica: function boundaries, call graph
- [ ] Pattern recognition: memset, memcpy, vblank wait, palette load
- [ ] Codegen pattern-aware (non più istruzione-per-istruzione)
- [ ] Test: 3 ROM producono screenshot DIVERSI tra loro

**Fase 4** (3 giorni): Coverage e validazione
- [ ] Codegen per LDM/STM, LDRH/STRH, MUL/MLA
- [ ] Codegen per Thumb (tutti gli opcode comuni)
- [ ] Golden screenshot con mGBA Lua API
- [ ] Confronto automatico transpiler vs mGBA
- [ ] Test: screenshot transpiler ≥80% simile a mGBA golden

**Fase 5** (2 giorni): Asset extraction e polimento
- [ ] Asset extraction corretta (tile, palette, sprites dalla ROM)
- [ ] DMA fix (pending flag, VBlank timing)
- [ ] Input handling (KEYINPUT register)
- [ ] Generazione .py standalone con tutto embeddato
- [ ] Documentazione finale

**Totale**: ~12 giorni per un transpiler funzionante con validazione visiva.

### 13.9 Perché questo è meglio dell'emulatore puro

| Aspetto | Emulatore (Rust) | Transpiler (proposto) |
|---------|------------------|----------------------|
| **Concetto** | Esegue ROM in tempo reale | Converte ROM → codice sorgente |
| **Output** | Solo runtime | File .py leggibile e modificabile |
| **Portabilità** | Dipende da Rust/PyO3 | Python + pygame (ovunque) |
| **Educazione** | Nasconde la logica | Mostra come funziona il gioco |
| **Debug** | Breakpoint in Rust | `print()` nel Python generato |
| **Modificabilità** | Impossibile | Apri il .py e cambia quello che vuoi |
| **Distribuzione** | .so compilato per ogni piattaforma | Singolo file .py |
| **Validazione** | Confronto con mGBA | Stesso, ma sul codice generato |

---

## 14. Riepilogo Finale

### Cosa abbiamo oggi
- Un transpiler che genera Python sintatticamente valido ma semanticamente rotto
- 41 ROM transpilano senza crash ma nessuna produce grafica corretta
- ~165K linee di codice tra Rust e Python, quasi tutto da riscrivere

### Cosa serve davvero
1. **Usare `unarm`** per disassemblare (100% coverage immediato)
2. **Registrare globali** nel codegen (fix critico #1)
3. **PPU basata su mGBA** reference (fix critico #2)
4. **Pattern-based codegen** (non più istruzione-per-istruzione)
5. **Golden screenshot con mGBA** per validazione automatica
6. **Test che verificano pixel output**, non solo "no crash"

### Sforzo stimato
- **Fase 1-2** (fondamenta + runtime): ~5 giorni
- **Fase 3-4** (codegen + coverage): ~5 giorni
- **Fase 5** (assets + polimento): ~2 giorni
- **Totale**: ~12 giorni per un transpiler funzionante end-to-end

