func pairOp<T>(f: (T, T) -> T, a: T, b: T): T {
    f(a, b)
}

func sum(a: Int64, b: Int64): Int64 {
    a + b
}

func diff(a: Int64, b: Int64): Int64 {
    a - b
}

func prod(a: Int64, b: Int64): Int64 {
    a * b
}

func unit(): Int64 {
    0
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
    println("unit=" + (unit()).toString())
    println("sum=" + (sum(1, 2)).toString())
    println("diff=" + (diff(5, 2)).toString())
    println("prod=" + (prod(3, 4)).toString())
    println("pad=" + (padAlpha()).toString())
    let out: Int64 = pairOp<Int64>({ v: Int64 => v + 1 }, 1, 2)
    println((out).toString())
}
