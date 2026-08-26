#[unsafe(no_mangle)]
pub extern "C" fn metacarp_rust_scale_add(scale: f64, x: f64, y: f64) -> f64 {
    scale * x + y
}

#[repr(C)]
pub struct RustPoint {
    pub x: f64,
    pub y: f64,
}

pub fn point_norm_squared(point: &RustPoint) -> f64 {
    point.x * point.x + point.y * point.y
}

pub fn point_translate(point: &mut RustPoint, dx: f64, dy: f64) {
    point.x += dx;
    point.y += dy;
}
