package benchmark;

import std.io;
import std.math;
import std.collections;

enum LogLevel: Int32 {
    Debug = 0,
    Info = 1,
    Warning = 2,
    Error = 3,
    Fatal = 4,
}

struct Point3D {
    x: Float64;
    y: Float64;
    z: Float64;
}

interface Drawable {
    func draw(): Unit;
    func name(): String;
}

interface Serializer {
    func serialize(): String;
}

class Rectangle: Drawable {
    origin: Point3D;
    width: Float64;
    height: Float64;

    func Rectangle(origin: Point3D, width: Float64, height: Float64) {
        this.origin = origin;
        this.width = width;
        this.height = height;
    }

    func area(): Float64 {
        return width * height;
    }

    func perimeter(): Float64 {
        return 2.0 * (width + height);
    }

    func draw(): Unit {
        io.println("Drawing rectangle");
    }

    func name(): String {
        return "Rectangle";
    }

    func scale(factor: Float64) {
        width = width * factor;
        height = height * factor;
    }
}

class Circle: Drawable {
    center: Point3D;
    radius: Float64;

    func Circle(center: Point3D, radius: Float64) {
        this.center = center;
        this.radius = radius;
    }

    func area(): Float64 {
        return math.pi * radius * radius;
    }

    func perimeter(): Float64 {
        return 2.0 * math.pi * radius;
    }

    func draw(): Unit {
        io.println("Drawing circle");
    }

    func name(): String {
        return "Circle";
    }

    func containsPoint(p: Point3D): Bool {
        var dx = p.x - center.x;
        var dy = p.y - center.y;
        var dz = p.z - center.z;
        var distSq = dx * dx + dy * dy + dz * dz;
        var maxDist = radius * radius;
        var result = false;
        if distSq <= maxDist {
            result = true;
        }
        return result;
    }
}

func clamp(value: Float64, minVal: Float64, maxVal: Float64): Float64 {
    if value < minVal {
        return minVal;
    }
    if value > maxVal {
        return maxVal;
    }
    return value;
}

func classifyTriangle(a: Float64, b: Float64, c: Float64): String {
    if a <= 0.0 || b <= 0.0 || c <= 0.0 {
        return "Invalid";
    }
    if a + b <= c || b + c <= a || a + c <= b {
        return "Invalid";
    }
    if a == b && b == c {
        return "Equilateral";
    }
    if a == b || b == c || a == c {
        return "Isosceles";
    }
    return "Scalene";
}

func sumOfSquares(limit: Int32): Int64 {
    var total: Int64 = 0;
    var i: Int32 = 1;
    while i <= limit {
        total = total + i * i;
        i = i + 1;
    }
    return total;
}

func fibonacci(n: Int32): Int64 {
    if n <= 1 {
        return n;
    }
    var a: Int64 = 0;
    var b: Int64 = 1;
    var i: Int32 = 2;
    while i <= n {
        var temp = a + b;
        a = b;
        b = temp;
        i = i + 1;
    }
    return b;
}

func computeGcd(a: Int64, b: Int64): Int64 {
    var x = a;
    var y = b;
    while y != 0 {
        var temp = y;
        y = x % y;
        x = temp;
    }
    return x;
}

func demonstrateMatch(value: Int32): String {
    match (value) {
        case 0 => "zero",
        case 1 => "one",
        case 2 => "two",
        case 3 => "three",
        case _ => "many",
    }
}

func recursiveHelper(n: Int32, depth: Int32): Int64 {
    if depth == 0 {
        return 1;
    }
    return n * recursiveHelper(n, depth - 1);
}

func computeFactorial(n: Int32): Int64 {
    if n <= 1 {
        return 1;
    }
    return n * computeFactorial(n - 1);
}

func isEven(value: Int32): Bool {
    var remainder = value % 2;
    var result = false;
    if remainder == 0 {
        result = true;
    }
    return result;
}

func isLeapYear(year: Int32): Bool {
    var result = false;
    if year % 400 == 0 {
        result = true;
    }
    if year % 4 == 0 && year % 100 != 0 {
        result = true;
    }
    return result;
}

func computePolynomial(x: Float64, a: Float64, b: Float64, c: Float64): Float64 {
    var result: Float64 = 0.0;
    var x2 = x * x;
    result = a * x2 + b * x + c;
    return result;
}

func complexCalculation(base: Float64, factor: Int32): Float64 {
    var result: Float64 = base;
    var i: Int32 = 0;
    while i < factor {
        result = result * 1.5;
        result = result + 3.0;
        if result > 1000.0 {
            result = result / 2.0;
        }
        i = i + 1;
    }
    return result;
}

func countdown(start: Int32) {
    var current = start;
    while current > 0 {
        io.print("Count: ");
        io.println(current);
        current = current - 1;
        if current == 5 {
            io.println("Halfway there");
        }
    }
}

func demonstrateNestedControl(limit: Int32, threshold: Int32): Int64 {
    var total: Int64 = 0;
    var i: Int32 = 0;
    while i < limit {
        var j: Int32 = 0;
        while j < limit {
            var val = i * limit + j;
            if val > threshold {
                total = total + val;
            }
            j = j + 1;
        }
        i = i + 1;
    }
    return total;
}

func stringDemo(first: String, last: String): String {
    var greeting = "Hello";
    return greeting;
}

func arithmeticSequence(a1: Float64, d: Float64, n: Int32): Float64 {
    var an = a1 + d * (n - 1);
    return an;
}

func geometricSequence(a1: Float64, r: Float64, n: Int32): Float64 {
    var result: Float64 = a1;
    var i: Int32 = 1;
    while i < n {
        result = result * r;
        i = i + 1;
    }
    return result;
}

func productOfRange(start: Int32, end: Int32): Int64 {
    var result: Int64 = 1;
    var i: Int32 = start;
    while i <= end {
        result = result * i;
        i = i + 1;
    }
    return result;
}

main() {
    var origin = Point3D { x: 0.0, y: 0.0, z: 0.0 };
    var rect = Rectangle(origin, 10.0, 5.0);
    var circ = Circle(origin, 7.0);
    var rectArea = rect.area();
    io.print("Rectangle area: ");
    io.println(rectArea);
    var circArea = circ.area();
    io.print("Circle area: ");
    io.println(circArea);
    rect.scale(2.0);
    var scaledArea = rect.area();
    io.print("Scaled area: ");
    io.println(scaledArea);
    var fact10 = computeFactorial(10);
    io.print("10! = ");
    io.println(fact10);
    var fib20 = fibonacci(20);
    io.print("fib(20) = ");
    io.println(fib20);
    var sumSq = sumOfSquares(100);
    io.print("Sum squares: ");
    io.println(sumSq);
    var triType = classifyTriangle(3.0, 4.0, 5.0);
    io.print("Triangle: ");
    io.println(triType);
    var label = demonstrateMatch(2);
    io.print("Match: ");
    io.println(label);
    var clamped = clamp(5.0, 0.0, 10.0);
    io.print("Clamped: ");
    io.println(clamped);
    var poly = computePolynomial(2.0, 1.0, 2.0, 3.0);
    io.print("Poly: ");
    io.println(poly);
    var complex = complexCalculation(10.0, 5);
    io.print("Complex: ");
    io.println(complex);
    var gcd = computeGcd(48, 18);
    io.print("gcd(48,18): ");
    io.println(gcd);
    var ev = isEven(42);
    var ly = isLeapYear(2024);
    var nested = demonstrateNestedControl(5, 10);
    io.print("Nested sum: ");
    io.println(nested);
    countdown(3);
    var arith = arithmeticSequence(2.0, 3.0, 5);
    io.print("Arithmetic: ");
    io.println(arith);
    var geo = geometricSequence(2.0, 2.0, 6);
    io.print("Geometric: ");
    io.println(geo);
    var prod = productOfRange(1, 5);
    io.print("Product: ");
    io.println(prod);
}
