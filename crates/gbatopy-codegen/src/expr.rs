use serde::{Deserialize, Serialize};
use std::fmt;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PythonExpr {
    Literal(String),
    Variable(String),
    BinaryOp {
        left: Box<PythonExpr>,
        op: String,
        right: Box<PythonExpr>,
    },
    UnaryOp {
        op: String,
        expr: Box<PythonExpr>,
    },
    Call {
        func: Box<PythonExpr>,
        args: Vec<PythonExpr>,
    },
    Subscript {
        value: Box<PythonExpr>,
        index: Box<PythonExpr>,
    },
    Attribute {
        value: Box<PythonExpr>,
        attr: String,
    },
    Conditional {
        condition: Box<PythonExpr>,
        true_val: Box<PythonExpr>,
        false_val: Box<PythonExpr>,
    },
    Ternary {
        condition: Box<PythonExpr>,
        true_expr: Box<PythonExpr>,
        false_expr: Box<PythonExpr>,
    },
}

impl fmt::Display for PythonExpr {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PythonExpr::Literal(s) => write!(f, "{}", s),
            PythonExpr::Variable(name) => write!(f, "{}", name),
            PythonExpr::BinaryOp { left, op, right } => {
                write!(f, "({} {} {})", left, op, right)
            }
            PythonExpr::UnaryOp { op, expr } => write!(f, "{}{}", op, expr),
            PythonExpr::Call { func, args } => {
                let args_str = args
                    .iter()
                    .map(|a| a.to_string())
                    .collect::<Vec<_>>()
                    .join(", ");
                write!(f, "{}({})", func, args_str)
            }
            PythonExpr::Subscript { value, index } => write!(f, "{}[{}]", value, index),
            PythonExpr::Attribute { value, attr } => write!(f, "{}.{}", value, attr),
            PythonExpr::Conditional {
                condition: _,
                true_val,
                false_val: _,
            } => {
                write!(f, "{}", true_val)
            }
            PythonExpr::Ternary {
                condition,
                true_expr,
                false_expr,
            } => {
                write!(f, "({} if {} else {})", true_expr, condition, false_expr)
            }
        }
    }
}

impl PythonExpr {
    pub fn literal(s: &str) -> Self {
        PythonExpr::Literal(s.to_string())
    }

    pub fn variable(name: &str) -> Self {
        PythonExpr::Variable(name.to_string())
    }

    pub fn constant(n: u32) -> Self {
        PythonExpr::Literal(format!("{}", n))
    }
}
