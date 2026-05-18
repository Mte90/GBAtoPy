use crate::expr::PythonExpr;
use crate::stmt::{PythonFunction, PythonModule, PythonStmt};
use gbatopy_ir::{IrExpr, IrFunction, IrModule, IrOp, IrValue};
use std::fs;
use std::path::{Path, PathBuf};

pub struct CodeGenerator {
    assets_dir: PathBuf,
}

impl CodeGenerator {
    pub fn new(assets_dir: &Path) -> Self {
        Self {
            assets_dir: assets_dir.to_path_buf(),
        }
    }

    fn load_template(&self, name: &str) -> Option<String> {
        let template_path = self.assets_dir.join("templates").join(name);
        fs::read_to_string(&template_path).ok()
    }

    pub fn generate(&self, module: &IrModule) -> PythonModule {
        let mut py_mod = PythonModule::new();
        for func in &module.functions {
            let py_func = self.generate_function(func);
            py_mod.functions.push(py_func);
        }
        let func_map = self.generate_func_map(module);
        py_mod.main_block.push(PythonStmt::Assign {
            target: PythonExpr::Variable("func_map".to_string()),
            value: func_map,
        });
        py_mod
    }

    fn generate_func_map(&self, module: &IrModule) -> PythonExpr {
        let mut entries = Vec::new();
        for func in &module.functions {
            // Use func.name as variable reference, not string literal
            entries.push(format!("0x{:08X}: {}", func.address, func.name));
        }
        let dict_content = entries.join(", ");
        // Return as Python dict literal (not string) so func names are variable references
        PythonExpr::literal(&format!("{{{}}}", dict_content))
    }

    fn generate_function(&self, func: &IrFunction) -> PythonFunction {
        let mut py_func = PythonFunction::new(&func.name);

        // Add global declaration for all registers at the start of each function
        let register_names: Vec<String> = (0..=15)
            .map(|r| format!("r{}", r))
            .chain([
                "cpsr_n".to_string(),
                "cpsr_z".to_string(),
                "cpsr_c".to_string(),
                "cpsr_v".to_string(),
                "cpsr".to_string(),
                "spsr".to_string(),
            ])
            .collect();
        py_func.body.push(PythonStmt::Global {
            names: register_names,
        });

        for block in &func.blocks {
            for expr in &block.statements {
                let py_stmt = self.translate_expr(expr);
                py_func.body.push(PythonStmt::Expression(py_stmt));
            }
        }
        py_func
    }

    fn translate_expr(&self, expr: &IrExpr) -> PythonExpr {
        match expr {
            IrExpr::Value(v) => self.translate_value(v),
            IrExpr::Op(op, args) => {
                let left = args
                    .get(0)
                    .map(|a| self.translate_expr(a))
                    .unwrap_or(PythonExpr::constant(0));
                let right = args
                    .get(1)
                    .map(|a| self.translate_expr(a))
                    .unwrap_or(PythonExpr::constant(0));
                match op {
                    IrOp::Not => PythonExpr::Call {
                        func: Box::new(PythonExpr::Variable("__invert__".to_string())),
                        args: vec![left],
                    },
                    IrOp::Neg => PythonExpr::UnaryOp {
                        op: "-".to_string(),
                        expr: Box::new(left),
                    },
                    _ => PythonExpr::BinaryOp {
                        left: Box::new(left),
                        op: self.op_to_str(op),
                        right: Box::new(right),
                    },
                }
            }
            IrExpr::Conditional {
                condition: _,
                true_val,
                false_val,
            } => PythonExpr::Ternary {
                condition: Box::new(PythonExpr::Variable("cond".to_string())),
                true_expr: Box::new(self.translate_expr(true_val)),
                false_expr: Box::new(self.translate_expr(false_val)),
            },
            IrExpr::Phi { sources } => {
                if let Some((_, val)) = sources.first() {
                    self.translate_expr(val)
                } else {
                    PythonExpr::constant(0)
                }
            }
        }
    }

    fn translate_value(&self, val: &IrValue) -> PythonExpr {
        match val {
            IrValue::Constant(n) => PythonExpr::constant(*n),
            IrValue::Register(r) => PythonExpr::Variable(format!("r{}", r)),
            IrValue::Variable { name, version, .. } => {
                PythonExpr::Variable(format!("{}_{}", name, version))
            }
            IrValue::Flags { .. } => PythonExpr::Variable("flags".to_string()),
        }
    }

    fn op_to_str(&self, op: &IrOp) -> String {
        match op {
            IrOp::Add => "+".into(),
            IrOp::Sub => "-".into(),
            IrOp::Mul => "*".into(),
            IrOp::Div => "//".into(),
            IrOp::Rem => "%".into(),
            IrOp::And => "&".into(),
            IrOp::Or => "|".into(),
            IrOp::Xor => "^".into(),
            IrOp::Shl => "<<".into(),
            IrOp::Shr => ">>".into(),
            IrOp::Asr => ">>".into(),
            IrOp::Ror => ">>".into(),
            IrOp::Eq => "==".into(),
            IrOp::Ne => "!=".into(),
            IrOp::Lt => "<".into(),
            IrOp::Le => "<=".into(),
            IrOp::Gt => ">".into(),
            IrOp::Ge => ">=".into(),
            _ => "+".into(),
        }
    }
}

impl Default for CodeGenerator {
    fn default() -> Self {
        Self::new(Path::new("assets"))
    }
}

impl CodeGenerator {
    pub fn generate_header(&self) -> Option<String> {
        self.load_template("header.py")
    }

    pub fn generate_asset_loader(&self) -> Option<String> {
        self.load_template("asset_loader.py")
    }

    pub fn generate_register_bridge(&self) -> Option<String> {
        self.load_template("register_bridge.py")
    }

    pub fn generate_helpers(&self) -> Option<String> {
        self.load_template("helpers.py")
    }

    pub fn generate_game_loop(&self) -> Option<String> {
        self.load_template("game_loop.py")
    }
}
