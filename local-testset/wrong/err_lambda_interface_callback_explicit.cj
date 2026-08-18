func seed(): Int64 {
    4
}

func tri(n: Int64): Int64 {
    n + n + n
}

interface Unary {
    func apply(x: Int64): Int64
}

class Scale <: Unary {
    let k: Int64
    public init(k0: Int64) {
        k = k0
    }
    public func apply(x: Int64): Int64 {
        x * k
    }
}

func runThrough<R>(u: Unary, x: Int64, cb: (Int64) -> R): R {
    cb(u.apply(x))
}

func padAlpha(): Int64 {
    1
}

func padBeta(n: Int64): Int64 {
    n + padAlpha()
}

func padGamma(a: Int64, b: Int64): Int64 {
    a + b
}

func padDelta(s: String): String {
    s
}

func padEpsilon(flag: Bool): Bool {
    flag
}

func padZeta(a: Int64, b: Int64, c: Int64): Int64 {
    a + b + c
}

func padEta(n: Int64): Int64 {
    if (n < 0) {
        0
    } else {
        n
    }
}

main(): Unit {
    println("seed=" + (seed()).toString())
    println("tri=" + (tri(2)).toString())
    let s: Scale = Scale(5)
    println("pad=" + (padAlpha()).toString())
    let out: String = runThrough<String>(s, 4, { v: Int64 => v + 1 })
    println(out)
}
