func k(): Int64 {
    1
}

interface I {
    func f(): Int64
}

class C <: I {
    public func f(): String {
        "x"
    }
}

func wrap(n: Int64): Int64 {
    n + k()
}

func bump(n: Int64): Int64 {
    n + 1
}

func neg(n: Int64): Int64 {
    -n
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
    println("wrap=" + (wrap(2)).toString())
    println("bump=" + (bump(1)).toString())
    println("neg=" + (neg(3)).toString())
    println("pad=" + (padAlpha()).toString())
    let x: I = C()
    println((x.f()).toString())
}
