use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Condition {
    Eq,
    Ne,
    Cs,
    Cc,
    Mi,
    Pl,
    Vs,
    Vc,
    Hi,
    Ls,
    Ge,
    Lt,
    Gt,
    Le,
    Al,
    Nv,
}

impl Condition {
    pub fn from_bits(bits: u8) -> Option<Condition> {
        match bits & 0xF {
            0b0000 => Some(Condition::Eq),
            0b0001 => Some(Condition::Ne),
            0b0010 => Some(Condition::Cs),
            0b0011 => Some(Condition::Cc),
            0b0100 => Some(Condition::Mi),
            0b0101 => Some(Condition::Pl),
            0b0110 => Some(Condition::Vs),
            0b0111 => Some(Condition::Vc),
            0b1000 => Some(Condition::Hi),
            0b1001 => Some(Condition::Ls),
            0b1010 => Some(Condition::Ge),
            0b1011 => Some(Condition::Lt),
            0b1100 => Some(Condition::Gt),
            0b1101 => Some(Condition::Le),
            0b1110 => Some(Condition::Al),
            0b1111 => Some(Condition::Nv),
            _ => None,
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            Condition::Eq => "eq",
            Condition::Ne => "ne",
            Condition::Cs => "cs",
            Condition::Cc => "cc",
            Condition::Mi => "mi",
            Condition::Pl => "pl",
            Condition::Vs => "vs",
            Condition::Vc => "vc",
            Condition::Hi => "hi",
            Condition::Ls => "ls",
            Condition::Ge => "ge",
            Condition::Lt => "lt",
            Condition::Gt => "gt",
            Condition::Le => "le",
            Condition::Al => "al",
            Condition::Nv => "nv",
        }
    }
}

pub fn decode_condition(bits: u8) -> Option<Condition> {
    Condition::from_bits(bits)
}

#[cfg(test)]
mod tests {
    use super::*;

    // === Condition::from_bits() tests ===

    #[test]
    fn test_from_bits_eq() {
        assert_eq!(Condition::from_bits(0b0000), Some(Condition::Eq));
        assert_eq!(Condition::from_bits(0x0), Some(Condition::Eq));
        assert_eq!(Condition::from_bits(0x10), Some(Condition::Eq)); // High bits ignored
    }

    #[test]
    fn test_from_bits_ne() {
        assert_eq!(Condition::from_bits(0b0001), Some(Condition::Ne));
        assert_eq!(Condition::from_bits(0x1), Some(Condition::Ne));
    }

    #[test]
    fn test_from_bits_cs() {
        assert_eq!(Condition::from_bits(0b0010), Some(Condition::Cs));
        assert_eq!(Condition::from_bits(0x2), Some(Condition::Cs));
    }

    #[test]
    fn test_from_bits_cc() {
        assert_eq!(Condition::from_bits(0b0011), Some(Condition::Cc));
        assert_eq!(Condition::from_bits(0x3), Some(Condition::Cc));
    }

    #[test]
    fn test_from_bits_mi() {
        assert_eq!(Condition::from_bits(0b0100), Some(Condition::Mi));
        assert_eq!(Condition::from_bits(0x4), Some(Condition::Mi));
    }

    #[test]
    fn test_from_bits_pl() {
        assert_eq!(Condition::from_bits(0b0101), Some(Condition::Pl));
        assert_eq!(Condition::from_bits(0x5), Some(Condition::Pl));
    }

    #[test]
    fn test_from_bits_vs() {
        assert_eq!(Condition::from_bits(0b0110), Some(Condition::Vs));
        assert_eq!(Condition::from_bits(0x6), Some(Condition::Vs));
    }

    #[test]
    fn test_from_bits_vc() {
        assert_eq!(Condition::from_bits(0b0111), Some(Condition::Vc));
        assert_eq!(Condition::from_bits(0x7), Some(Condition::Vc));
    }

    #[test]
    fn test_from_bits_hi() {
        assert_eq!(Condition::from_bits(0b1000), Some(Condition::Hi));
        assert_eq!(Condition::from_bits(0x8), Some(Condition::Hi));
    }

    #[test]
    fn test_from_bits_ls() {
        assert_eq!(Condition::from_bits(0b1001), Some(Condition::Ls));
        assert_eq!(Condition::from_bits(0x9), Some(Condition::Ls));
    }

    #[test]
    fn test_from_bits_ge() {
        assert_eq!(Condition::from_bits(0b1010), Some(Condition::Ge));
        assert_eq!(Condition::from_bits(0xA), Some(Condition::Ge));
    }

    #[test]
    fn test_from_bits_lt() {
        assert_eq!(Condition::from_bits(0b1011), Some(Condition::Lt));
        assert_eq!(Condition::from_bits(0xB), Some(Condition::Lt));
    }

    #[test]
    fn test_from_bits_gt() {
        assert_eq!(Condition::from_bits(0b1100), Some(Condition::Gt));
        assert_eq!(Condition::from_bits(0xC), Some(Condition::Gt));
    }

    #[test]
    fn test_from_bits_le() {
        assert_eq!(Condition::from_bits(0b1101), Some(Condition::Le));
        assert_eq!(Condition::from_bits(0xD), Some(Condition::Le));
    }

    #[test]
    fn test_from_bits_al() {
        assert_eq!(Condition::from_bits(0b1110), Some(Condition::Al));
        assert_eq!(Condition::from_bits(0xE), Some(Condition::Al));
    }

    #[test]
    fn test_from_bits_nv() {
        assert_eq!(Condition::from_bits(0b1111), Some(Condition::Nv));
        assert_eq!(Condition::from_bits(0xF), Some(Condition::Nv));
    }

    #[test]
    fn test_from_bits_invalid() {
        // All values are valid since we mask with 0xF
        for i in 0u8..=255 {
            assert!(Condition::from_bits(i).is_some());
        }
    }

    // === Condition::name() tests ===

    #[test]
    fn test_name_eq() {
        assert_eq!(Condition::Eq.name(), "eq");
    }

    #[test]
    fn test_name_ne() {
        assert_eq!(Condition::Ne.name(), "ne");
    }

    #[test]
    fn test_name_cs() {
        assert_eq!(Condition::Cs.name(), "cs");
    }

    #[test]
    fn test_name_cc() {
        assert_eq!(Condition::Cc.name(), "cc");
    }

    #[test]
    fn test_name_mi() {
        assert_eq!(Condition::Mi.name(), "mi");
    }

    #[test]
    fn test_name_pl() {
        assert_eq!(Condition::Pl.name(), "pl");
    }

    #[test]
    fn test_name_vs() {
        assert_eq!(Condition::Vs.name(), "vs");
    }

    #[test]
    fn test_name_vc() {
        assert_eq!(Condition::Vc.name(), "vc");
    }

    #[test]
    fn test_name_hi() {
        assert_eq!(Condition::Hi.name(), "hi");
    }

    #[test]
    fn test_name_ls() {
        assert_eq!(Condition::Ls.name(), "ls");
    }

    #[test]
    fn test_name_ge() {
        assert_eq!(Condition::Ge.name(), "ge");
    }

    #[test]
    fn test_name_lt() {
        assert_eq!(Condition::Lt.name(), "lt");
    }

    #[test]
    fn test_name_gt() {
        assert_eq!(Condition::Gt.name(), "gt");
    }

    #[test]
    fn test_name_le() {
        assert_eq!(Condition::Le.name(), "le");
    }

    #[test]
    fn test_name_al() {
        assert_eq!(Condition::Al.name(), "al");
    }

    #[test]
    fn test_name_nv() {
        assert_eq!(Condition::Nv.name(), "nv");
    }

    // === Round-trip tests ===

    #[test]
    fn test_round_trip_all_conditions() {
        // Test that from_bits(name) round-trips correctly for all 16 conditions
        for bits in 0u8..16 {
            let cond = Condition::from_bits(bits).unwrap();
            let name = cond.name();
            // Verify name is lowercase and matches expected suffix
            assert!(
                name.chars().all(|c| c.is_ascii_lowercase()),
                "Condition {:?} name '{}' should be lowercase",
                cond,
                name
            );
        }
    }

    #[test]
    fn test_condition_properties() {
        // EQ/NE are inverses
        assert_eq!(Condition::Eq.name(), "eq");
        assert_eq!(Condition::Ne.name(), "ne");

        // CS/CC are inverses
        assert_eq!(Condition::Cs.name(), "cs");
        assert_eq!(Condition::Cc.name(), "cc");

        // MI/PL are inverses
        assert_eq!(Condition::Mi.name(), "mi");
        assert_eq!(Condition::Pl.name(), "pl");

        // VS/VC are inverses
        assert_eq!(Condition::Vs.name(), "vs");
        assert_eq!(Condition::Vc.name(), "vc");

        // HI/LS are inverses
        assert_eq!(Condition::Hi.name(), "hi");
        assert_eq!(Condition::Ls.name(), "ls");

        // GE/LT are inverses
        assert_eq!(Condition::Ge.name(), "ge");
        assert_eq!(Condition::Lt.name(), "lt");

        // GT/LE are inverses
        assert_eq!(Condition::Gt.name(), "gt");
        assert_eq!(Condition::Le.name(), "le");

        // AL and NV are special cases
        assert_eq!(Condition::Al.name(), "al");
        assert_eq!(Condition::Nv.name(), "nv");
    }

    #[test]
    fn test_decode_condition() {
        // Test the decode_condition wrapper function
        assert_eq!(decode_condition(0x0), Some(Condition::Eq));
        assert_eq!(decode_condition(0x1), Some(Condition::Ne));
        assert_eq!(decode_condition(0xE), Some(Condition::Al));
        assert_eq!(decode_condition(0xF), Some(Condition::Nv));
    }

    #[test]
    fn test_condition_debug_display() {
        // Verify Debug trait works (derived)
        let cond = Condition::Eq;
        let debug_str = format!("{:?}", cond);
        assert_eq!(debug_str, "Eq");
    }

    #[test]
    fn test_condition_clone_copy() {
        // Verify Clone and Copy traits work (derived)
        let cond1 = Condition::Eq;
        let cond2 = cond1; // Copy
        assert_eq!(cond1, cond2);

        let cond3 = cond1.clone(); // Clone
        assert_eq!(cond1, cond3);
    }

    #[test]
    fn test_condition_equality() {
        // Verify PartialEq works (derived)
        assert_eq!(Condition::Eq, Condition::Eq);
        assert_ne!(Condition::Eq, Condition::Ne);
        assert_eq!(Condition::from_bits(0x0).unwrap(), Condition::Eq);
    }
}
