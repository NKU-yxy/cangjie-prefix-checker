func run<R>(f: () -> R): R {
    f()
}

func base(): Int64 {
    40
}

func inc(n: Int64): Int64 {
    n + 1
}

func tag(): String {
    "infer-run"
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
    println(tag())
    println("base=" + (base()).toString())
    println("inc=" + (inc(1)).toString())
    println("pad=" + (padAlpha()).toString())
    let x: Int64 = run({ => "s" })
    println((x).toString())
}
