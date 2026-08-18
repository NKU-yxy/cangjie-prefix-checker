func flagOn(): Bool {
    true
}

func flagOff(): Bool {
    false
}

func pick(flag: Bool): String {
    if (flag) {
        "on"
    } else {
        "off"
    }
}

func asInt(b: Bool): Int64 {
    if (b) {
        1
    } else {
        0
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
    let on: Bool = flagOn()
    let off: Bool = flagOff()
    println(pick(on))
    println(pick(off))
    println("asInt=" + (asInt(on)).toString())
    println("pad=" + (padEpsilon(on)).toString())
    let bad: Int64 = -on
    println((bad).toString())
}
