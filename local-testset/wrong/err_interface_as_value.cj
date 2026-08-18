func seed(): Int64 {
    0
}

interface I {
    func f(): Int64
}

class C <: I {
    public func f(): Int64 {
        seed()
    }
}

func via(obj: I): Int64 {
    obj.f()
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
    let c: C = C()
    println("via=" + (via(c)).toString())
    println("pad=" + (padAlpha()).toString())
    let bad: I = I
    println((bad.f()).toString())
}
