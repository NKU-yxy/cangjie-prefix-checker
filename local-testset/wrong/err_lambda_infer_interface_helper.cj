func prelude(): Int64 {
    1
}

func label(): String {
    "bind"
}

interface Host {
    func run<R>(f: () -> R): R
}

class H <: Host {
    public func run<R>(f: () -> R): R {
        f()
    }
}

func zero(): Int64 {
    0
}

func flag(): Bool {
    true
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
    println("prelude=" + (prelude()).toString())
    println(label())
    println("zero=" + (zero()).toString())
    println("flag=" + (flag()).toString())
    println("pad=" + (padEpsilon(flag())).toString())
    let h: H = H()
    let x: String = h.run({ => 1 })
    println(x)
}
