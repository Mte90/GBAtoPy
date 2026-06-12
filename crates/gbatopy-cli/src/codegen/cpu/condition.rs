/// CMP (Compare): Rd - Rm, update flags only (no result stored)
pub fn generate_cmp_instruction(ops: &[String]) -> String {
    // ops[0] = Rd (register), ops[1] = Rm (register or immediate)
    let rd = &ops[0];
    let rm = &ops[1];

    format!(
        r#"# CMP {rd}, {rm}
result_cmp = {rd} - {rm}
result_cmp = result_cmp & 0xFFFFFFFF  # Ensure 32-bit
cpsr['n'] = (result_cmp >> 31) & 1
cpsr['z'] = 1 if result_cmp == 0 else 0
# Carry: 1 if no borrow (result >= 0 in unsigned)
cpsr['c'] = 1 if ({rd} >= {rm}) else 0
# Overflow: signed overflow in subtraction
if ({rd} >= 0 and {rm} < 0 and result_cmp < 0) or ({rd} < 0 and {rm} >= 0 and result_cmp >= 0):
    cpsr['v'] = 1
else:
    cpsr['v'] = 0"#
    )
}

/// CMN (Compare Negative): Rd + Rm, update flags only
/// CMN (Compare Negative): Rd + Rm, update flags only
pub fn generate_cmn_instruction(ops: &[String]) -> String {
    let rd = &ops[0];
    let rm = &ops[1];

    format!(
        r#"# CMN {rd}, {rm}
result_cmn = ({rd} + {rm}) & 0xFFFFFFFF
cpsr['n'] = (result_cmn >> 31) & 1
cpsr['z'] = 1 if result_cmn == 0 else 0
# Carry: 1 if overflow occurred (sum >= 2^32)
cpsr['c'] = 1 if ({rd} + {rm}) >= 0x100000000 else 0
# Overflow: signed overflow in addition
rd_s = {rd} if {rd} < 0x80000000 else {rd} - 0x100000000
rm_s = {rm} if {rm} < 0x80000000 else {rm} - 0x100000000
if (rd_s > 0 and rm_s > 0 and result_cmn >= 0x80000000) or (rd_s < 0 and rm_s < 0 and result_cmn < 0x80000000):
    cpsr['v'] = 1
else:
    cpsr['v'] = 0"#
    )
}

/// TST (Test): Rd AND Rm, update flags only
pub fn generate_tst_instruction(ops: &[String]) -> String {
    let rd = &ops[0];
    let rm = &ops[1];

    format!(
        r#"# TST {rd}, {rm}
result_tst = {rd} & {rm}
cpsr['n'] = (result_tst >> 31) & 1
cpsr['z'] = 1 if result_tst == 0 else 0
cpsr['c'] = 0  # No carry for AND
cpsr['v'] = 0  # No overflow for AND"#
    )
}

/// TEQ (Test Equivalence): Rd EOR Rm, update flags only
pub fn generate_teq_instruction(ops: &[String]) -> String {
    let rd = &ops[0];
    let rm = &ops[1];

    format!(
        r#"# TEQ {rd}, {rm}
result_teq = {rd} ^ {rm}
cpsr['n'] = (result_teq >> 31) & 1
cpsr['z'] = 1 if result_teq == 0 else 0
cpsr['c'] = 0  # No carry for EOR
cpsr['v'] = 0  # No overflow for EOR"#
    )
}

/// ADD (Add): Rd + Rm, update flags
pub fn generate_add_instruction(ops: &[String]) -> String {
    let rd = &ops[0];
    let rm = &ops[1];

    format!(
        r#"# ADD {rd}, {rm}
result_add = ({rd} + {rm}) & 0xFFFFFFFF
{rd} = result_add
cpsr['n'] = (result_add >> 31) & 1
cpsr['z'] = 1 if result_add == 0 else 0
cpsr['c'] = 1 if ({rd} + {rm}) >= 0x100000000 else 0
# Signed overflow: both positive and result negative, or both negative and result positive
rd_signed = {rd} if {rd} < 0x80000000 else {rd} - 0x100000000
rm_signed = {rm} if {rm} < 0x80000000 else {rm} - 0x100000000
result_signed = result_add if result_add < 0x80000000 else result_add - 0x100000000
if (rd_signed > 0 and rm_signed > 0 and result_signed < 0) or (rd_signed < 0 and rm_signed < 0 and result_signed >= 0):
    cpsr['v'] = 1
else:
    cpsr['v'] = 0"#
    )
}

/// ADC (Add with Carry): Rd + Rm + C, update flags
pub fn generate_adc_instruction(ops: &[String]) -> String {
    let rd = &ops[0];
    let rm = &ops[1];

    format!(
        r#"# ADC {rd}, {rm}
result_adc = ({rd} + {rm} + cpsr['c']) & 0xFFFFFFFF
{rd} = result_adc
cpsr['n'] = (result_adc >> 31) & 1
cpsr['z'] = 1 if result_adc == 0 else 0
cpsr['c'] = 1 if ({rd} + {rm} + cpsr['c']) >= 0x100000000 else 0
# Signed overflow
rd_signed = {rd} if {rd} < 0x80000000 else {rd} - 0x100000000
rm_signed = {rm} if {rm} < 0x80000000 else {rm} - 0x100000000
result_signed = result_adc if result_adc < 0x80000000 else result_adc - 0x100000000
if (rd_signed > 0 and rm_signed > 0 and result_signed < 0) or (rd_signed < 0 and rm_signed < 0 and result_signed >= 0):
    cpsr['v'] = 1
else:
    cpsr['v'] = 0"#
    )
}

/// SUB (Subtract): Rd - Rm, update flags
pub fn generate_sub_instruction(ops: &[String]) -> String {
    let rd = &ops[0];
    let rm = &ops[1];

    format!(
        r#"# SUB {rd}, {rm}
result_sub = ({rd} - {rm}) & 0xFFFFFFFF
{rd} = result_sub
cpsr['n'] = (result_sub >> 31) & 1
cpsr['z'] = 1 if result_sub == 0 else 0
cpsr['c'] = 1 if {rd} >= {rm} else 0  # No borrow
# Signed overflow
rd_signed = {rd} if {rd} < 0x80000000 else {rd} - 0x100000000
rm_signed = {rm} if {rm} < 0x80000000 else {rm} - 0x100000000
result_signed = result_sub if result_sub < 0x80000000 else result_sub - 0x100000000
if (rd_signed > 0 and rm_signed < 0 and result_signed < 0) or (rd_signed < 0 and rm_signed > 0 and result_signed >= 0):
    cpsr['v'] = 1
else:
    cpsr['v'] = 0"#
    )
}

/// SBC (Subtract with Carry): Rd - Rm + C - 1, update flags
pub fn generate_sbc_instruction(ops: &[String]) -> String {
    let rd = &ops[0];
    let rm = &ops[1];

    format!(
        r#"# SBC {rd}, {rm}
# SBC = Rd - Rm + C - 1 = Rd - Rm + (C - 1)
result_sbc = ({rd} - {rm} + cpsr['c'] - 1) & 0xFFFFFFFF
{rd} = result_sbc
cpsr['n'] = (result_sbc >> 31) & 1
cpsr['z'] = 1 if result_sbc == 0 else 0
cpsr['c'] = 1 if {rd} >= {rm} + (1 - cpsr['c']) else 0
# Signed overflow
rd_signed = {rd} if {rd} < 0x80000000 else {rd} - 0x100000000
rm_signed = {rm} if {rm} < 0x80000000 else {rm} - 0x100000000
result_signed = result_sbc if result_sbc < 0x80000000 else result_sbc - 0x100000000
if (rd_signed > 0 and rm_signed < 0 and result_signed < 0) or (rd_signed < 0 and rm_signed > 0 and result_signed >= 0):
    cpsr['v'] = 1
else:
    cpsr['v'] = 0"#
    )
}

/// RSB (Reverse Subtract): Rm - Rd, update flags
pub fn generate_rsb_instruction(ops: &[String]) -> String {
    let rd = &ops[0];
    let rm = &ops[1];

    format!(
        r#"# RSB {rd}, {rm}
result_rsb = ({rm} - {rd}) & 0xFFFFFFFF
{rd} = result_rsb
cpsr['n'] = (result_rsb >> 31) & 1
cpsr['z'] = 1 if result_rsb == 0 else 0
cpsr['c'] = 1 if {rm} >= {rd} else 0  # No borrow
# Signed overflow
rm_signed = {rm} if {rm} < 0x80000000 else {rm} - 0x100000000
rd_signed = {rd} if {rd} < 0x80000000 else {rd} - 0x100000000
result_signed = result_rsb if result_rsb < 0x80000000 else result_rsb - 0x100000000
if (rm_signed > 0 and rd_signed < 0 and result_signed < 0) or (rm_signed < 0 and rd_signed > 0 and result_signed >= 0):
    cpsr['v'] = 1
else:
    cpsr['v'] = 0"#
    )
}

/// RSC (Reverse Subtract with Carry): Rm - Rd + C - 1, update flags
pub fn generate_rsc_instruction(ops: &[String]) -> String {
    let rd = &ops[0];
    let rm = &ops[1];

    format!(
        r#"# RSC {rd}, {rm}
# RSC = Rm - Rd + C - 1
result_rsc = ({rm} - {rd} + cpsr['c'] - 1) & 0xFFFFFFFF
{rd} = result_rsc
cpsr['n'] = (result_rsc >> 31) & 1
cpsr['z'] = 1 if result_rsc == 0 else 0
cpsr['c'] = 1 if {rm} >= {rd} + (1 - cpsr['c']) else 0
# Signed overflow
rm_signed = {rm} if {rm} < 0x80000000 else {rm} - 0x100000000
rd_signed = {rd} if {rd} < 0x80000000 else {rd} - 0x100000000
result_signed = result_rsc if result_rsc < 0x80000000 else result_rsc - 0x100000000
if (rm_signed > 0 and rd_signed < 0 and result_signed < 0) or (rm_signed < 0 and rd_signed > 0 and result_signed >= 0):
    cpsr['v'] = 1
else:
    cpsr['v'] = 0"#
    )
}
