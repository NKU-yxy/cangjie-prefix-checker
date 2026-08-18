class Runner {
    public static func eval<R>(f: () -> R): R {
        f()
    }
}

func ten(): Int64 {
    10
}

func double(n: Int64): Int64 {
    n + n
}

func label(): String {
    "runner"
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
    println(label())
    println("ten=" + (ten()).toString())
    println("dbl=" + (double(3)).toString())
    println("pad=" + (padAlpha()).toString())
    let x: Int64 = Runner.eval<Int64>({ => "x" })
    println((x).toString())
}
