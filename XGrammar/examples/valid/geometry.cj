package geometry

import std.math

class Point {
    x: Float64
    y: Float64

    func distance(other: Point): Float64 {
        var dx = x - other.x
        var dy = y - other.y
        return math.sqrt(dx * dx + dy * dy)
    }
}

func main() {
    var p1 = Point { x: 0.0, y: 0.0 }
    var p2 = Point { x: 3.0, y: 4.0 }
    let dist = p1.distance(p2)
    math.println(dist)
}
