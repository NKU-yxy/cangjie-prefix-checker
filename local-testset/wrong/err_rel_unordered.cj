func cmpStr(a: String, b: String): Int64 {
    a.compare(b)
}

func left(): String {
    "a"
}

func right(): String {
    "b"
}

func same(a: String, b: String): Bool {
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
    let a: String = left()
    let b: String = right()
    println("cmp=" + (cmpStr(a, b)).toString())
    println("same=" + (same(a, b)).toString())
    println("pad=" + (padDelta(a)).toString())
    let bad: Bool = a < b
    println((bad).toString())
}
