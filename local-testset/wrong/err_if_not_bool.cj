func absv(x: Int64): Int64 {
    if (x < 0) {
        -x
    } else {
        x
    }
}

func neg(x: Int64): Int64 {
    -x
}

func tag(x: Int64): String {
    if (x == 0) {
        "zero"
    } else {
        "other"
    }
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
    let v: Int64 = 0
    let w: Int64 = absv(v)
    println("w=" + (w).toString())
    println("tag=" + (tag(v)).toString())
    println("neg=" + (neg(w)).toString())
    println("pad=" + (padAlpha()).toString())
    let label: String = if (v) {
        "nonzero"
    } else {
        "zero"
    }
    println("label=" + (label).toString())
}
