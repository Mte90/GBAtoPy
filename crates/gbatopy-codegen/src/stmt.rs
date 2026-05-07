use super::expr::PythonExpr;
use serde::{Deserialize, Serialize};
use std::fmt;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PythonStmt {
    Assign {
        target: PythonExpr,
        value: PythonExpr,
    },
    AugAssign {
        target: PythonExpr,
        op: String,
        value: PythonExpr,
    },
    If {
        condition: PythonExpr,
        body: Vec<PythonStmt>,
        else_body: Vec<PythonStmt>,
    },
    While {
        condition: PythonExpr,
        body: Vec<PythonStmt>,
    },
    For {
        target: PythonExpr,
        iter: PythonExpr,
        body: Vec<PythonStmt>,
    },
    Return {
        value: Option<PythonExpr>,
    },
    Expression(PythonExpr),
    Import {
        module: String,
        names: Vec<String>,
    },
    FunctionDef(PythonFunction),
    Global {
        names: Vec<String>,
    },
}

impl fmt::Display for PythonStmt {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PythonStmt::Assign { target, value } => {
                write!(f, "{} = {}", target, value)
            }
            PythonStmt::AugAssign { target, op, value } => {
                write!(f, "{} {}= {}", target, op, value)
            }
            PythonStmt::If {
                condition,
                body,
                else_body,
            } => {
                write!(f, "if {}:\n", condition)?;
                for stmt in body {
                    write!(f, "    {}\n", stmt)?;
                }
                if !else_body.is_empty() {
                    write!(f, "else:\n")?;
                    for stmt in else_body {
                        write!(f, "    {}\n", stmt)?;
                    }
                }
                Ok(())
            }
            PythonStmt::While { condition, body } => {
                write!(f, "while {}:\n", condition)?;
                for stmt in body {
                    write!(f, "    {}\n", stmt)?;
                }
                Ok(())
            }
            PythonStmt::For { target, iter, body } => {
                write!(f, "for {} in {}:\n", target, iter)?;
                for stmt in body {
                    write!(f, "    {}\n", stmt)?;
                }
                Ok(())
            }
            PythonStmt::Return { value } => {
                if let Some(v) = value {
                    write!(f, "return {}", v)
                } else {
                    write!(f, "return")
                }
            }
            PythonStmt::Expression(expr) => {
                write!(f, "{}", expr)
            }
            PythonStmt::Import { module, names } => {
                if names.is_empty() {
                    write!(f, "import {}", module)
                } else {
                    write!(f, "from {} import {}", module, names.join(", "))
                }
            }
            PythonStmt::FunctionDef(func) => {
                write!(f, "def {}({}):", func.name, func.params.join(", "))
            }
            PythonStmt::Global { names } => {
                let names_str = names.join(", ");
                write!(f, "global {}", names_str)
            }
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PythonFunction {
    pub name: String,
    pub params: Vec<String>,
    pub body: Vec<PythonStmt>,
    pub return_type: Option<String>,
    pub decorators: Vec<String>,
}

impl PythonFunction {
    pub fn new(name: &str) -> Self {
        Self {
            name: name.to_string(),
            params: vec![],
            body: vec![],
            return_type: None,
            decorators: vec![],
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PythonModule {
    pub imports: Vec<(String, Vec<String>)>,
    pub functions: Vec<PythonFunction>,
    pub main_block: Vec<PythonStmt>,
}

impl PythonModule {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn add_import(&mut self, module: &str, names: Vec<String>) {
        self.imports.push((module.to_string(), names));
    }
}
