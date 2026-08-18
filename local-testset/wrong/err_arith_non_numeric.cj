func add2(a: Int64, b: Int64): Int64 {
    a + b
}

func concat2(a: String, b: String): String {
    a + b
}

func double(n: Int64): Int64 {
    n + n
}

func label(flag: Bool): String {
    if (flag) {
        "yes"
    } else {
        "no"
    }
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
    let a: Int64 = 3
    let b: Int64 = 4
    println("add2=" + (add2(a, b)).toString())
    println("dbl=" + (double(a)).toString())
    println("concat=" + concat2("a", "b").toString())
    println("lbl=" + (label(true)).toString())
    println("bump=" + (bump(b)).toString())
    let bad: Int64 = true + 1
    println((bad).toString())
}
