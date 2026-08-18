func invoke<T>(f: (T) -> T, x: T): T {
    f(x)
}

func ident(n: Int64): Int64 {
    n
}

func double(n: Int64): Int64 {
    n + n
}

func zero(): Int64 {
    0
}

func add1(n: Int64): Int64 {
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
    println("ident=" + (ident(3)).toString())
    println("double=" + (double(2)).toString())
    println("zero=" + (zero()).toString())
    println("add1=" + (add1(4)).toString())
    println("pad=" + (padAlpha()).toString())
    let bad: Int64 = invoke<Int64>({ v: String => "x" }, 0)
    println((bad).toString())
}
