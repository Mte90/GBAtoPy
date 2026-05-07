use crate::blocks::IrBlock;

pub struct SsaBuilder;

impl SsaBuilder {
    pub fn new() -> Self {
        Self
    }

    pub fn build_function(&self, blocks: &mut [IrBlock]) {
        for block in blocks.iter_mut() {
            for stmt in block.statements.iter_mut() {
                self.process_expr(stmt);
            }
        }
    }

    fn process_expr(&self, _expr: &mut crate::IrExpr) {}
}

impl Default for SsaBuilder {
    fn default() -> Self {
        Self::new()
    }
}
