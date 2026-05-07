use serde::{Deserialize, Serialize};

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
        func: String,
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
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PythonStmt {
    Assign {
        target: String,
        value: PythonExpr,
    },
    AugAssign {
        target: String,
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
        target: String,
        iter: PythonExpr,
        body: Vec<PythonStmt>,
    },
    Return {
        value: Option<PythonExpr>,
    },
    Expression {
        expr: PythonExpr,
    },
    Import {
        module: String,
        names: Vec<String>,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PythonFunction {
    pub name: String,
    pub params: Vec<String>,
    pub body: Vec<PythonStmt>,
    pub return_type: Option<String>,
    pub decorators: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PythonModule {
    pub imports: Vec<PythonStmt>,
    pub functions: Vec<PythonFunction>,
    pub main_block: Vec<PythonStmt>,
}

pub type Result<T> = std::result::Result<T, super::Error>;
