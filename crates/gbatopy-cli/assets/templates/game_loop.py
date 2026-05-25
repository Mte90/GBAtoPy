def run_transpiled(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    def ror(v, a):
        a = a & 31
        return ((v >> a) | (v << (32 - a))) & 0xFFFFFFFF
    fc = 0; mi = 1000000; ic = 0
    print(f"PC=0x{r[15]:08X}")
    while ic < mi:
        pc = r[15]
        if pc not in func_map:
            print(f"Unknown PC: 0x{pc:08X}"); break
        func_map[pc](); ic += 1
        if r[15] == pc: print(f"Loop at 0x{pc:08X}"); break
        if ic % 10000 == 0: print(f"{ic} instrs, PC=0x{r[15]:08X}")
        if frame_limit and fc >= frame_limit: break
        if ic % 1000 == 0: fc += 1
    print(f"Done: {ic} instrs")
    return fc

def run_with_pygame(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    pygame.init()
    if not headless:
        screen = pygame.display.set_mode((240 * scale, 160 * scale))
        pygame.display.set_caption("GBAtoPy")
    else:
        screen = pygame.Surface((240 * scale, 160 * scale))
    clock = pygame.time.Clock()
    fc = 0; running = True; mi = 1000000; ic = 0
    print(f"PC=0x{r[15]:08X}")
    while running and ic < mi:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
        pc = r[15]
        if pc in func_map:
            func_map[pc]()
        else:
            print(f"Unknown PC: 0x{pc:08X}"); break
        ic += 1
        if r[15] == pc: print(f"Loop at 0x{pc:08X}"); break
        render_rom_pattern(screen, ROM_DATA)
        pygame.display.flip()
        clock.tick(60); fc += 1
        if frame_limit and fc >= frame_limit: break
    if screenshot_path:
        pygame.image.save(screen, screenshot_path)
        print(f"Screenshot: {screenshot_path}")
    pygame.quit()
    return fc

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--frame", type=int)
    parser.add_argument("--screenshot", type=str)
    parser.add_argument("--scale", type=int, default=1)
    args = parser.parse_args()
    frames = run_with_pygame(headless=args.headless, frame_limit=args.frame, screenshot_path=args.screenshot, scale=args.scale)
    print(f"{frames} frames")
