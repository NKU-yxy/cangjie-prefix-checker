func headChar(s: String): Rune {
    s.get(0).getOrThrow()
}

func empty(s: String): Bool {
    s.isEmpty()
}

func slen(s: String): Int64 {
    s.size
}

func tailHint(s: String): String {
    if (s.size < 2) {
        s
    } else {
        "multi"
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
    let s: String = "hi"
    println("empty=" + (empty(s)).toString())
    println("slen=" + (slen(s)).toString())
    println("tail=" + (tailHint(s)).toString())
    println("head=" + (headChar(s)).toString())
    println("pad=" + (padDelta(s)).toString())
    let bad: Bool = s.contains(1)
    println((bad).toString())
}
