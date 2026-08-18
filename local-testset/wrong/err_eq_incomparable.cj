func one(): Int64 {
    1
}

func tag(): String {
    "x"
}

func sameInt(a: Int64, b: Int64): Bool {
    a == b
}

func sameStr(a: String, b: String): Bool {
    a == b
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
    let a: Int64 = one()
    let s: String = tag()
    println("a=" + (a).toString())
    println(s)
    println("sameInt=" + (sameInt(a, a)).toString())
    println("sameStr=" + (sameStr(s, s)).toString())
    println("pad=" + (padDelta(s)).toString())
    let bad: Bool = 1 == "x"
    println((bad).toString())
}
