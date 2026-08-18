func slen(s: String): Int64 {
    s.size
}

func empty(s: String): Bool {
    s.isEmpty()
}

func head(s: String): String {
    if (s.isEmpty()) {
        s
    } else {
        "h"
    }
}

func greet(): String {
    "hello"
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
    let s: String = greet()
    println("len=" + (slen(s)).toString())
    println("empty=" + (empty(s)).toString())
    println("head=" + (head(s)).toString())
    println("pad=" + (padDelta(s)).toString())
    let bad: String = s.missing()
    println(bad)
}
