func unitTag(): Int64 {
    0
}

func describe(): String {
    "describe"
}

func note(): String {
    "iface"
}

func pad(): Int64 {
    0
}

interface I {
    func f(): Unit
}

class C <: I {}

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
    let u: Int64 = unitTag()
    println("u=" + (u).toString())
    println(describe())
    println(note())
    println("pad=" + (pad()).toString())
    let x: I = C()
    x.f()
}
