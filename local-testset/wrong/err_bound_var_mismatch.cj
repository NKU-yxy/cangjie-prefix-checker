func echo(s: String): String {
    s
}

func slen(s: String): Int64 {
    s.size
}

func greet(): String {
    "hi"
}

func bump(n: Int64): Int64 {
    n + 1
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
    let msg: String = greet()
    println(echo(msg))
    println("len=" + (slen(msg)).toString())
    let n: Int64 = 7
    println("bump=" + (bump(n)).toString())
    println("pad=" + (padBeta(n)).toString())
    let bad: String = echo(n)
    println(bad)
}
