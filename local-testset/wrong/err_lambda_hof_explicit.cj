import std.collection.*

func mapInPlace<T>(xs: ArrayList<T>, f: (T) -> T): Unit {
    for (i in 0..xs.size) {
        xs[i] = f(xs[i])
    }
}

func triplet(): ArrayList<Int64> {
    ArrayList<Int64>([1, 2, 3])
}

func sum3(a: Int64, b: Int64, c: Int64): Int64 {
    a + b + c
}

func dump(tag: String, xs: ArrayList<Int64>): Unit {
    println((tag).toString() + ": " + (xs[0]).toString() + " " + (xs[1]).toString() + " " + (xs[2]).toString())
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
    let a: ArrayList<Int64> = triplet()
    println("sum=" + (sum3(a[0], a[1], a[2])).toString())
    dump("before", a)
    println("pad=" + (padAlpha()).toString())
    let _step: Unit = mapInPlace<Int64>(a, { v: Int64 => "bad" })
    dump("after", a)
}
